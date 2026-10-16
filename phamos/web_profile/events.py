"""Events section of the Web Profile pages (/de/veranstaltungen, /en/events).

The public record is Marketing Content itself (published events only). What a page may show is decided
here, once: ``item["data"]`` is an allow-list. Organizer and contact person email addresses, the Email
Group, attendee data and internal links never reach a template (phamos/phamos#1492 privacy rule).

The offer (price incl. VAT, sale open, seats left) comes from ``phamos.marketing.ticketing.offer`` and
is cached with the items (``sections.CACHE_SECONDS``); every order re-validates it server-side and
clears the cache.
"""

import frappe
from babel.dates import format_date, format_time
from babel.numbers import format_currency
from frappe import _
from frappe.utils import get_datetime, get_system_timezone, get_url, getdate, now_datetime, nowdate

from phamos.web_profile.i18n import localized
from phamos.web_profile.socials import normalize_url
from phamos.web_profile.utils import slugify

FIELDS = ["name", "title", "subtitle", "event_type", "status", "date_note", "starts_on", "ends_on", "route", "image",
	"location", "city", "map_link", "organizer_name", "organizer_logo", "organizer_website_link", "contact_profile",
	"registration_open", "max_attendees", "ticket_item", "tc_name", "email_group"]
DATE_FORMAT = {"de": "EEEE, d. MMMM y", "en": "EEEE, d MMMM y"}
SHORT_DATE = {"de": "d. MMM y", "en": "d MMM y"}
LOCALES = {"de": "de_DE", "en": "en_GB"}


def _event_offer(name):
	"""Wrapper so tests can patch the offer without the accounting setup."""
	from phamos.marketing.ticketing import offer

	return offer(name)


def _iso(value):
	"""ISO 8601 with the site's UTC offset (Datetime fields are naive, in the system time zone)."""
	if not value:
		return None
	import pytz

	return pytz.timezone(get_system_timezone()).localize(get_datetime(value).replace(microsecond=0)).isoformat()


def when(record, lang):
	"""{"date", "time", "line", "short"} in the page language; the date note when no date is set."""
	if not record.starts_on:
		note = record.date_note or ""
		return {"date": note, "time": "", "line": note, "short": note}
	locale = LOCALES[lang]
	start, end = get_datetime(record.starts_on), get_datetime(record.ends_on) if record.ends_on else None
	if end and end.date() != start.date():
		date = f"{format_date(start, SHORT_DATE[lang], locale=locale)} – {format_date(end, SHORT_DATE[lang], locale=locale)}"
	else:
		date = format_date(start, DATE_FORMAT[lang], locale=locale)
	time = format_time(start, "HH:mm", locale=locale)
	if end and end.date() == start.date():
		time = f"{time}–{format_time(end, 'HH:mm', locale=locale)}"
	return {"date": date, "time": time, "line": f"{date} · {time}", "short": format_date(start, SHORT_DATE[lang], locale=locale)}


def price_label(offer, lang):
	if not offer or offer.get("free"):
		return _("Free")
	return format_currency(offer["gross"], offer["currency"], locale=LOCALES[lang])


def is_upcoming(record):
	end = record.ends_on or record.starts_on
	if not end:
		return True  # date still open ("Expected: spring 2027")
	return get_datetime(end) >= now_datetime()


def availability(record, offer):
	"""(chip, badge) for tiles: what a visitor most needs to know before clicking."""
	if record.status == "Cancelled":
		return _("Cancelled"), _("Cancelled")
	if not is_upcoming(record):
		return None, None
	if not offer:
		return None, None
	if offer.get("reason") == "sold_out" or offer.get("spots_left") == 0:
		return _("Sold out"), _("Sold out")
	if offer.get("sale_open"):
		return (_("Free") if offer.get("free") else _("Tickets available")), None
	if offer.get("reason") == "not_started":
		return _("Ticket sale opens soon"), None
	return None, None


def load_events(lang):
	from phamos.web_profile.sections import _facet, _item, attach_texts

	records = attach_texts("Marketing Content", frappe.get_all("Marketing Content", filters={"published": 1},
		fields=FIELDS))
	names = [r.name for r in records]
	speakers, sponsors = {}, {}
	if names:
		for row in frappe.get_all("Marketing Event Speaker", filters={"parenttype": "Marketing Content",
				"parent": ["in", names], "published": 1}, fields=["parent", "full_name", "image", "topic", "person"],
				order_by="idx asc"):
			speakers.setdefault(row.parent, []).append(row)
		for row in frappe.get_all("Marketing Event Sponsor", filters={"parenttype": "Marketing Content",
				"parent": ["in", names], "published": 1},
				fields=["parent", "sponsor_name", "logo", "url", "additional_information"], order_by="idx asc"):
			sponsors.setdefault(row.parent, []).append(row)
	person_slugs = dict(frappe.get_all("Person Web Profile", filters={"published": 1}, fields=["name", "route"],
		as_list=True)) if speakers else {}

	items = []
	today = getdate(nowdate())
	for r in records:
		offer = _event_offer(r.name) if r.registration_open or r.ticket_item else None
		offer = dict(offer) if offer else None
		upcoming = is_upcoming(r)
		w = when(r, lang)
		title = localized(r, "title", lang, fallback=True) or r.title
		item = _item("events", r, lang, title, r.route, subtitle=w["line"], image=r.image)
		item["summary"] = localized(r, "summary", lang)
		item["body"] = localized(r, "content", lang)
		_facet(item, "when", "upcoming" if upcoming else "past", "")
		_facet(item, "when", "all", "")
		if r.event_type:
			_facet(item, "event_type", slugify(r.event_type), _(r.event_type))
		if r.city:
			_facet(item, "city", slugify(r.city), r.city)
		chip, badge = availability(r, offer)
		item["chips"] = [c for c in (_(r.event_type) if r.event_type else None, r.city, chip) if c]
		if badge:
			item["badge"] = badge
		start = getdate(r.starts_on) if r.starts_on else None
		# Upcoming first, soonest on top; then past events, most recent on top; open dates after upcoming.
		if upcoming:
			days = (start - today).days if start else 10**5
			item["sort"]["date"] = [0, days, title.lower()]
		else:
			item["sort"]["date"] = [1, (today - start).days if start else 10**5, title.lower()]
		item["search"] = " ".join(filter(None, [title, r.subtitle, r.city, r.location, r.organizer_name,
			*(s.full_name for s in speakers.get(r.name, []))])).lower()
		item["data"] = {
			"starts_on": _iso(r.starts_on), "ends_on": _iso(r.ends_on), "date_note": r.date_note,
			"when": w, "upcoming": upcoming, "cancelled": r.status == "Cancelled",
			"location": r.location, "city": r.city, "map_url": normalize_url(r.map_link),
			"organizer": {"name": r.organizer_name, "logo": r.organizer_logo,
				"url": normalize_url(r.organizer_website_link)},
			"key_person": r.contact_profile,
			"speakers": [{"name": s.full_name, "image": s.image, "topic": s.topic,
				"person_slug": person_slugs.get(s.person)} for s in speakers.get(r.name, [])],
			"sponsors": [{"name": s.sponsor_name, "logo": s.logo, "url": normalize_url(s.url),
				"info": s.additional_information} for s in sponsors.get(r.name, [])],
			"offer": _public_offer(offer, lang) if upcoming and r.status != "Cancelled" else None,
			"has_newsletter": bool(r.email_group) and upcoming,
			"terms": r.tc_name,
			"languages": sorted(r.texts),
			"ics": bool(r.starts_on),
		}
		items.append(item)
	return items


def _public_offer(offer, lang):
	if not offer:
		return None
	return {
		"free": offer["free"], "gross": offer["gross"], "net": offer["net"], "tax_rate": offer["tax_rate"],
		"currency": offer["currency"], "price_label": price_label(offer, lang), "item_name": offer["item_name"],
		"sale_open": offer["sale_open"], "reason": offer["reason"], "spots_left": offer["spots_left"],
		"max_per_order": offer["max_per_order"],
		"sale_until": _iso(offer["sale_until"]) if offer.get("sale_until") else None,
	}


# --- profile page -----------------------------------------------------------------------------------------


def build(item, lang):
	"""Facts, overview, schema, hero, actions, blocks, ticket data and notice for an event page."""
	from phamos.web_profile.sections import ORGANIZATION, item_url

	d = item.data
	offer = d.get("offer")
	# Date, time and venue are in the page header (hero); facts show each piece of information once.
	facts = []
	facts.append({"label": _("Type"), "value": item.labels.get("event_type", {}).get((item.facets.get("event_type") or [None])[0])})
	if offer:
		value = offer["price_label"] if offer["free"] else _("{0} incl. VAT").format(offer["price_label"])
		facts.append({"label": _("Price"), "value": value})
		if offer.get("spots_left") is not None and offer["sale_open"]:
			facts.append({"label": _("Seats left"), "value": str(offer["spots_left"])})
	org = d.get("organizer") or {}
	if org.get("name"):
		facts.append({"label": _("Organizer"), "value": org["name"],
			"links": [{"value": org["name"], "url": org["url"], "external": True}] if org.get("url") else None})

	overview = []
	if d.get("cancelled"):
		overview.append(_("This event has been cancelled."))
	elif d["when"]["date"]:
		overview.append(_("{0}: {1} in {2}.").format(item.title, d["when"]["line"], d.get("city") or d.get("location") or _("online"))
			if d.get("city") or d.get("location") else _("{0}: {1}.").format(item.title, d["when"]["line"]))

	actions = []
	if offer and offer["sale_open"]:
		actions.append({"label": _("Register") if offer["free"] else _("Buy ticket"), "dialog": "tickets", "primary": True})
	elif offer and d["upcoming"]:
		reason = {"sold_out": _("Sold out"), "not_started": _("Ticket sale has not started yet"),
			"ended": _("Ticket sale has ended")}.get(offer.get("reason"))
		if reason:
			actions.append({"label": reason, "note": True})
	if d.get("has_newsletter"):
		actions.append({"label": _("Keep me posted"), "dialog": "subscribe"})
	if d.get("ics"):
		actions.append({"label": _("Add to calendar"), "download": True,
			"url": f"/api/method/phamos.marketing.web.ics?event={item.slug}&lang={lang}"})

	blocks = []
	if d.get("speakers"):
		blocks.append({"kind": "people", "title": _("Speakers"), "entries": [
			{"title": s["name"], "subtitle": "", "image": s["image"], "body": s["topic"],
				"url": item_url("people", s["person_slug"], lang) if s.get("person_slug") else None}
			for s in d["speakers"]]})
	if d.get("sponsors"):
		blocks.append({"kind": "logos", "title": _("Sponsors"), "entries": [
			{"title": s["name"], "image": s["logo"], "url": s["url"], "body": s["info"]} for s in d["sponsors"]]})

	hero = {"image": item.image, "badge": item.get("badge"), "lines": [
		{"kind": "when", "text": d["when"]["line"], "datetime": d.get("starts_on")},
		{"kind": "where", "text": ", ".join(filter(None, [d.get("location"), d.get("city")])), "url": d.get("map_url")},
	]}

	schema = None
	if d.get("starts_on"):
		place = {"@type": "Place", "name": d.get("location") or d.get("city"),
			"address": {"@type": "PostalAddress", "addressLocality": d.get("city")}}
		schema = {"@type": "Event", "name": item.title, "startDate": d["starts_on"], "endDate": d.get("ends_on") or d["starts_on"],
			"eventStatus": "https://schema.org/EventCancelled" if d.get("cancelled") else "https://schema.org/EventScheduled",
			"eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode", "location": place,
			"organizer": {"@type": "Organization", "name": org["name"], "url": org.get("url")} if org.get("name") else ORGANIZATION,
			"performer": [{"@type": "Person", "name": s["name"]} for s in d.get("speakers") or []] or None,
			"description": item.summary or None}
		if offer:
			schema["isAccessibleForFree"] = bool(offer["free"])
			schema["offers"] = {"@type": "Offer", "price": offer["gross"], "priceCurrency": offer["currency"] or "EUR",
				"url": get_url(item.url), "validThrough": offer.get("sale_until"),
				"availability": "https://schema.org/InStock" if offer["sale_open"] else "https://schema.org/SoldOut"
					if offer.get("reason") == "sold_out" else "https://schema.org/PreOrder"
					if offer.get("reason") == "not_started" else "https://schema.org/Discontinued"}

	ticket = None
	if offer and offer["sale_open"]:
		terms_html = frappe.db.get_value("Terms and Conditions", d["terms"], "terms") if d.get("terms") else None
		ticket = {**offer, "terms_html": terms_html, "countries": _countries(lang)}

	notice = None
	if d.get("languages") and lang not in d["languages"]:
		notice = _("This event is described in English only.") if "en" in d["languages"] else _("This event is described in German only.")
	return {"facts": facts, "overview": " ".join(overview), "schema": schema, "hero": hero, "actions": actions,
		"blocks": blocks, "ticket": ticket, "notice": notice}


def _countries(lang):
	"""Country options for the billing address: the usual ones first."""
	first = ["Germany", "Austria", "Switzerland"]
	rest = [c for c in frappe.get_all("Country", pluck="name", order_by="name asc") if c not in first]
	return [{"value": c, "label": _(c)} for c in first + rest]
