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
from frappe.utils import cint, get_datetime, strip_html, get_system_timezone, get_url, getdate, now_datetime, nowdate

from phamos.marketing.location import address_line, is_online, map_links
from phamos.web_profile.i18n import localized
from phamos.web_profile.socials import normalize_url
from phamos.web_profile.utils import slugify

FIELDS = ["name", "title", "subtitle", "event_type", "status", "date_note", "starts_on", "ends_on", "route", "image",
	"attendance_mode", "location", "street", "postal_code", "city", "country", "latitude", "longitude", "organizer_is_phamos", "organizer", "organizer_name", "organizer_logo",
	"organizer_website_link", "contact_profile", "going_count", "maybe_count", "not_going_count", "show_bookings_publicly",
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
				fields=["parent", "stakeholder", "sponsor_label", "sponsor_name", "logo", "url", "additional_information"],
				order_by="idx asc"):
			sponsors.setdefault(row.parent, []).append(row)
	person_slugs = dict(frappe.get_all("Person Web Profile", filters={"published": 1}, fields=["name", "route"],
		as_list=True)) if speakers else {}

	stakeholders = _named_stakeholders(lang)
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
		online = is_online(r)
		place = _("Online") if online else r.city
		if online:
			_facet(item, "city", "online", place)
		elif r.city:
			_facet(item, "city", slugify(r.city), r.city)
		chip, badge = availability(r, offer)
		if offer and cint(r.show_bookings_publicly) and cint(offer.get("booked")) and chip not in (_("Sold out"), _("Cancelled")):
			capacity = cint(offer.get("capacity"))
			chip = _("{0}/{1} booked").format(offer["booked"], capacity) if capacity else _("{0} booked").format(offer["booked"])
		item["chips"] = [c for c in (_(r.event_type) if r.event_type else None, place, chip) if c]
		if badge:
			item["badge"] = badge
		start = getdate(r.starts_on) if r.starts_on else None
		if start:
			item["numbers"]["month"] = start.year * 12 + start.month - 1  # the "Period" slider, by month
		# Upcoming first, soonest on top; then past events, most recent on top; open dates after upcoming.
		if upcoming:
			days = (start - today).days if start else 10**5
			item["sort"]["date"] = [0, days, title.lower()]
		else:
			item["sort"]["date"] = [1, (today - start).days if start else 10**5, title.lower()]
		organizer = _organizer(r, stakeholders)
		event_sponsors = [s for s in (_sponsor(row, stakeholders) for row in sponsors.get(r.name, [])) if s]
		# The meeting link of an online event is private: it is neither searchable nor in the item data.
		item["search"] = " ".join(filter(None, [title, r.subtitle, place, None if online else r.location, organizer.get("name"),
			*(s["name"] for s in event_sponsors),
			*(s.full_name for s in speakers.get(r.name, []))])).lower()
		item["data"] = {
			"starts_on": _iso(r.starts_on), "ends_on": _iso(r.ends_on), "date_note": r.date_note,
			"when": w, "upcoming": upcoming, "cancelled": r.status == "Cancelled",
			"online": online, "location": None if online else r.location,
			# In person: the address and the map pin (the map view, phamos/phamos#1666, reads these).
			**({} if online else {"street": r.street, "postal_code": r.postal_code, "city": r.city,
				"country": r.country, "latitude": r.latitude if r.latitude or r.longitude else None,
				"longitude": r.longitude if r.latitude or r.longitude else None}),
			"organizer": organizer,
			# Named stakeholders (sponsor or organizer): their profile pages list this event.
			"stakeholders": sorted({s["stakeholder"] for s in event_sponsors if s.get("stakeholder")}
				| ({organizer["stakeholder"]} if organizer.get("stakeholder") else set())),
			"key_person": r.contact_profile,
			"speakers": [{"name": s.full_name, "image": s.image, "topic": s.topic,
				"person_slug": person_slugs.get(s.person)} for s in speakers.get(r.name, [])],
			"sponsors": event_sponsors,
			"offer": _public_offer(offer, lang) if upcoming and r.status != "Cancelled" else None,
			"interest": {"yes": cint(r.going_count), "maybe": cint(r.maybe_count), "no": cint(r.not_going_count)}
				if upcoming and r.status != "Cancelled" else None,
			"has_newsletter": bool(r.email_group) and upcoming,
			"terms": r.tc_name,
			"languages": sorted(r.texts),
			"ics": bool(r.starts_on),
		}
		items.append(item)
	return items


def month_span(values, selected):
	"""Span of the "Period" slider: a calendar window around today (next 12 months for upcoming events,
	last 12 for past ones, both for all), widened to every event in view."""
	today = getdate(nowdate())
	now = today.year * 12 + today.month - 1
	when = (selected.get("when") or ["upcoming"])[0]
	low = now if when == "upcoming" else now - 11
	high = now if when == "past" else now + 11
	return min([low, *values]), max([high, *values])


def _named_stakeholders(lang):
	"""{Stakeholder Web Profile name: {title, logo, url, website}} of published profiles that may be named.
	Anonymous stakeholders are never named through an event (phamos/phamos#1492 privacy rule)."""
	from phamos.web_profile.sections import _stakeholder_pages, item_url

	extra = {r.name: r for r in frappe.get_all("Stakeholder Web Profile", filters={"published": 1},
		fields=["name", "image", "website"])}
	result = {}
	for page in _stakeholder_pages(lang).values():
		if page.named and page.name in extra:
			result[page.name] = {"title": page.title, "logo": extra[page.name].image,
				"url": item_url(page.section, page.slug, lang), "website": normalize_url(extra[page.name].website)}
	return result


def _organizer(record, stakeholders):
	if record.organizer_is_phamos:
		return {"name": "phamos GmbH", "phamos": True}
	if record.organizer:
		page = stakeholders.get(record.organizer)
		if not page:
			return {}  # not (yet) approved to be named: show no organizer rather than an anonymous one
		return {"name": page["title"], "logo": page["logo"], "url": page["url"], "website": page["website"],
			"stakeholder": record.organizer}
	return {"name": record.organizer_name, "logo": record.organizer_logo,
		"website": normalize_url(record.organizer_website_link)} if record.organizer_name else {}


def _sponsor(row, stakeholders):
	if row.stakeholder:
		page = stakeholders.get(row.stakeholder)
		if not page:
			return None
		return {"name": page["title"], "logo": page["logo"], "url": page["url"], "label": row.sponsor_label,
			"info": row.additional_information, "stakeholder": row.stakeholder}
	if not row.sponsor_name:
		return None
	return {"name": row.sponsor_name, "logo": row.logo, "url": normalize_url(row.url), "external": True,
		"label": row.sponsor_label, "info": row.additional_information}


def _public_offer(offer, lang):
	if not offer:
		return None
	money = lambda value: format_currency(value, offer["currency"] or "EUR", locale=LOCALES[lang])
	prices = [{"title": p["title"], "price_label": money(p["gross"]), "remaining": p["remaining"], "quota": p["quota"],
		"until": format_date(get_datetime(p["valid_until"]), SHORT_DATE[lang], locale=LOCALES[lang]) if p["valid_until"] else None,
		"from": format_date(get_datetime(p["valid_from"]), SHORT_DATE[lang], locale=LOCALES[lang]) if p["valid_from"] else None,
		"available": p["available"], "upcoming": p["upcoming"]} for p in offer.get("prices") or [] if not p["ended"]]
	return {"prices": prices, "price_title": offer.get("price_title"),
		"free": offer["free"], "gross": offer["gross"], "net": offer["net"], "tax_rate": offer["tax_rate"],
		"currency": offer["currency"], "price_label": price_label(offer, lang), "item_name": offer["item_name"],
		"sale_open": offer["sale_open"], "reason": offer["reason"], "spots_left": offer["spots_left"],
		"max_per_order": offer["max_per_order"],
		"sale_until": _iso(offer["sale_until"]) if offer.get("sale_until") else None,
		"capacity": offer.get("capacity"),
		# Public booking count (setting on the event): attendees only, never names.
		"booked": cint(offer.get("booked")) if offer.get("show_bookings") else None,
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
		if offer.get("price_title") and len(offer.get("prices") or []) > 1:
			value = f"{value} ({offer['price_title']})"
		facts.append({"label": _("Price"), "value": value})
		if offer.get("spots_left") is not None and offer["sale_open"]:
			facts.append({"label": _("Seats left"), "value": str(offer["spots_left"])})
	org = d.get("organizer") or {}
	if org.get("name"):
		link = {"value": org["name"], "url": org["url"]} if org.get("url") else \
			{"value": org["name"], "url": org["website"], "external": True} if org.get("website") else None
		facts.append({"label": _("Organizer"), "value": org["name"], "links": [link] if link else None})

	overview = []
	if d.get("cancelled"):
		overview.append(_("This event has been cancelled."))
	elif d["when"]["date"]:
		overview.append(_("{0}: {1}, online.").format(item.title, d["when"]["line"]) if d.get("online")
			else _("{0}: {1} in {2}.").format(item.title, d["when"]["line"], d.get("city") or d.get("location"))
			if d.get("city") or d.get("location") else _("{0}: {1}.").format(item.title, d["when"]["line"]))

	# Sidebar, in this order: the buy button with its price, what is special about the price, bookings;
	# then (template) the interest question; then the secondary actions.
	actions = []
	if offer and offer["sale_open"]:
		actions.append({"label": _("Register for free") if offer["free"] else _("Buy from {0}").format(offer["price_label"]),
			"dialog": "tickets", "primary": True, "sub": None if offer["free"] else _("incl. VAT")})
		note = price_note(offer)
		if note:
			actions.append({"label": note, "hint": True})
	elif offer and d["upcoming"]:
		reason = {"sold_out": _("Sold out"), "not_started": _("Ticket sale has not started yet"),
			"ended": _("Ticket sale has ended")}.get(offer.get("reason"))
		if reason:
			actions.append({"label": reason, "note": True})
	if offer and offer.get("booked"):
		capacity = cint(offer.get("capacity"))
		label = _("{0} of {1} seats taken").format(offer["booked"], capacity) if capacity else \
			_("{0} registrations").format(offer["booked"])
		actions.append({"label": label, "bookings": True,
			"percent": min(100, round(100 * offer["booked"] / capacity)) if capacity else None})
	if d.get("ics"):
		actions.append({"label": _("Add to calendar"), "download": True, "secondary": True, "pair": True,
			"url": f"/api/method/phamos.marketing.web.ics?event={item.slug}&lang={lang}"})
		if d["upcoming"]:
			actions.append({"label": _("Create reminder"), "dialog": "reminder", "secondary": True, "pair": True})
	if d.get("has_newsletter"):
		actions.append({"label": _("Keep me posted"), "dialog": "subscribe", "secondary": True})

	blocks = []
	if d.get("speakers"):
		from phamos.web_profile.sections import get_items

		people = {p.slug: p for p in get_items("people", lang)} if any(sp.get("person_slug") for sp in d["speakers"]) else {}
		entries = []
		for sp in d["speakers"]:
			person = people.get(sp.get("person_slug"))
			if person and person.masked:
				person = None  # an anonymous profile is never tied to a named speaker
			entries.append({"title": sp["name"] or (person.title if person else ""), "subtitle": strip_html(sp["topic"] or "")[:120],
				"image": sp["image"] or (person.image if person else None), "url": person.url if person else None,
				"initials": "".join(w[0] for w in (sp["name"] or "?").split()[:2]).upper()})
		blocks.append({"kind": "people", "title": _("Speakers"), "entries": entries})
	if d.get("sponsors"):
		blocks.append({"kind": "logos", "title": _("Sponsors"), "entries": [
			{"title": s["name"], "image": s["logo"], "url": s.get("url"), "external": s.get("external"),
				"subtitle": s.get("label"), "initials": "".join(w[0] for w in (s["name"] or "?").split()[:2]).upper(),
				"info": strip_html(s.get("info") or "").strip()}
			for s in d["sponsors"]]})

	hero = {"image": item.image, "badge": item.get("badge"), "lines": [
		{"kind": "when", "text": d["when"]["line"], "datetime": d.get("starts_on")},
		{"kind": "where", "text": _("Online")} if d.get("online") else {"kind": "where", "text": address_line(d),
			"maps": map_links(d.get("latitude"), d.get("longitude"), d.get("location") or address_line(d))},
	]}

	schema = None
	if d.get("starts_on"):
		schema = {"@type": "Event", "name": item.title, "startDate": d["starts_on"], "endDate": d.get("ends_on") or d["starts_on"],
			"eventStatus": "https://schema.org/EventCancelled" if d.get("cancelled") else "https://schema.org/EventScheduled",
			**_schema_location(d, item),
			"organizer": ORGANIZATION if org.get("phamos") or not org.get("name") else {"@type": "Organization",
				"name": org["name"], "url": org.get("website") or (get_url(org["url"]) if org.get("url") else None)},
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
		from phamos.web_profile.chrome import company_footer

		company = company_footer()
		ticket = {**offer, "terms_html": terms_html, "countries": _countries(lang),
			"sender": " · ".join(filter(None, [company.get("name"), *(company.get("address_lines") or [])])),
			"today": format_date(getdate(nowdate()), "d. MMMM y" if lang == "de" else "d MMMM y", locale=LOCALES[lang])}

	notice = None
	if d.get("languages") and lang not in d["languages"]:
		notice = _("This event is described in English only.") if "en" in d["languages"] else _("This event is described in German only.")
	return {"facts": facts, "overview": " ".join(overview), "schema": schema, "hero": hero, "actions": actions,
		"blocks": blocks, "ticket": ticket, "notice": notice, "interest": d.get("interest")}


def _schema_location(d, item):
	"""Online: a virtual location pointing to the event page (never the meeting link). In person: the place
	with its postal address and coordinates."""
	if d.get("online"):
		return {"eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
			"location": {"@type": "VirtualLocation", "url": get_url(item.url)}}
	address = {"@type": "PostalAddress", "streetAddress": d.get("street"), "postalCode": d.get("postal_code"),
		"addressLocality": d.get("city"),
		"addressCountry": (frappe.db.get_value("Country", d["country"], "code") or "").upper() if d.get("country") else None}
	place = {"@type": "Place", "name": d.get("location") or d.get("city"),
		"address": {k: v for k, v in address.items() if v}}
	if d.get("latitude") is not None:
		place["geo"] = {"@type": "GeoCoordinates", "latitude": d["latitude"], "longitude": d["longitude"]}
	return {"eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode", "location": place}


def price_note(offer):
	""""Early Bird until 30 Nov 2026 · 12 left · then 199,00 €" (the price itself is on the button)."""
	if offer["free"]:
		return ""
	parts = []
	prices = offer.get("prices") or []
	index = next((i for i, p in enumerate(prices) if p["title"] == offer.get("price_title")), None)
	if index is not None and len(prices) > 1:
		current = prices[index]
		parts.append(_("{0} until {1}").format(current["title"], current["until"]) if current.get("until")
			else current["title"])
		if current.get("remaining") is not None:
			parts.append(_("{0} left").format(current["remaining"]))
		following = next((p for p in prices[index + 1:] if p.get("remaining") != 0), None)
		if following:
			parts.append(_("then {0}").format(following["price_label"]))
	return " · ".join(parts)


def _countries(lang):
	"""Country options for the billing address: the usual ones first."""
	first = ["Germany", "Austria", "Switzerland"]
	rest = [c for c in frappe.get_all("Country", pluck="name", order_by="name asc") if c not in first]
	return [{"value": c, "label": _(c)} for c in first + rest]
