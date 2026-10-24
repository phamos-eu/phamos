"""Guest endpoints of the event pages (/de/veranstaltungen/<slug>, /en/events/<slug>).

Same rules as the contact dialog (phamos.web_profile.contact): POST only, rate-limited per IP, a
hidden honeypot field, consent checkboxes, strict validation. Events are found by their public slug
among the published items, never by a document name sent by the browser. The order itself is
``phamos.marketing.ticketing.register_attendees``, which validates everything again.
"""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, get_datetime, get_system_timezone, get_url, now_datetime

from phamos.marketing import ticketing
from phamos.marketing.defaults import MAX_ATTENDEES_PER_ORDER
from phamos.marketing.utils import normalize_email
from phamos.web_profile.i18n import DEFAULT_LANGUAGE, LANGUAGES
from phamos.web_profile.sections import clear_section, find_item

PHONE = re.compile(r"[0-9 +()./-]{5,40}")
VAT_ID = re.compile(r"[A-Z]{2}[A-Z0-9]{2,13}")
MAX_TEXT = 140


def _lang(lang):
	lang = lang if lang in LANGUAGES else DEFAULT_LANGUAGE
	frappe.local.lang = lang
	return lang


def _event(slug, lang):
	item = find_item("events", (slug or "").strip(), lang)
	if not item:
		frappe.throw(_("This event is not available."), frappe.DoesNotExistError)
	return item


def _json(value, default):
	if value in (None, ""):
		return default
	if isinstance(value, (dict, list)):
		return value
	try:
		return json.loads(value)
	except ValueError:
		frappe.throw(_("Invalid request."))


def _text(value, required=False, label=None, limit=MAX_TEXT):
	value = (value or "").strip()
	if required and not value:
		frappe.throw(_("Please fill in: {0}").format(label))
	return value[:limit]


def _person(raw, email_required, label):
	person = raw if isinstance(raw, dict) else {}
	name = _text(person.get("full_name"), True, label)
	if len(name) < 2:
		frappe.throw(_("Please enter the full name: {0}").format(label))
	email = (person.get("email") or "").strip()
	if email_required or email:
		email = normalize_email(email)
	return {"full_name": name, "email": email, "phone": _text(person.get("phone"), limit=40)}


def _companions(raw):
	people = _json(raw, [])
	if not isinstance(people, list):
		frappe.throw(_("Invalid request."))
	if len(people) >= MAX_ATTENDEES_PER_ORDER:
		frappe.throw(_("At most {0} tickets per order.").format(MAX_ATTENDEES_PER_ORDER))
	return [_person(p, False, _("Ticket holder {0}").format(i + 2)) for i, p in enumerate(people)]


def _billing(raw, free):
	billing = _json(raw, None)
	if free and not billing:
		return None
	if not isinstance(billing, dict):
		frappe.throw(_("Please fill in the billing details."))
	result = {
		"full_name": _text(billing.get("full_name"), True, _("Name")),
		"email": normalize_email(billing.get("email")),
		"phone": _text(billing.get("phone"), limit=40),
		"is_company": cint(billing.get("is_company")),
		"company": _text(billing.get("company")),
		"vat_id": re.sub(r"\s", "", _text(billing.get("vat_id"), limit=20)).upper(),
		"address_line1": _text(billing.get("address_line1"), True, _("Street and number")),
		"address_line2": _text(billing.get("address_line2")),
		"postcode": _text(billing.get("postcode"), True, _("Postcode"), limit=20),
		"city": _text(billing.get("city"), True, _("City")),
		"country": _text(billing.get("country"), True, _("Country")),
	}
	if result["phone"] and not PHONE.fullmatch(result["phone"]):
		frappe.throw(_("Please enter a valid phone number or leave it empty."))
	if result["is_company"] and not result["company"]:
		frappe.throw(_("Please enter the company name for the invoice."))
	if not result["is_company"]:
		result["company"], result["vat_id"] = "", ""
	if result["vat_id"] and not VAT_ID.fullmatch(result["vat_id"]):
		frappe.throw(_("Please enter a valid VAT ID (e.g. DE123456789) or leave it empty."))
	if not frappe.db.exists("Country", result["country"]):
		frappe.throw(_("Please choose a country."))
	return result


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60 * 60)
def order_tickets(event, lang, contact, attends=1, companions=None, billing=None, expected_total=None, hold_id=None,
		website=None):
	"""The binding order ("Zahlungspflichtig bestellen"). No consent checkboxes: the order is a contract
	(Art. 6 (1) b GDPR), the terms apply through the notice above the button; the optional marketing
	questions come afterwards (``save_consents``)."""
	if website:
		return {"ok": True}  # honeypot: hidden from people, filled in by bots
	lang = _lang(lang)
	item = _event(event, lang)
	offer = item.data.get("offer")
	if not offer or not offer.get("sale_open"):
		frappe.throw(_("Ticket sales for this event are closed."))
	main = _person(_json(contact, {}), True, _("Your name"))
	others = _companions(companions)
	if not cint(attends) and not others:
		frappe.throw(_("Please add at least one ticket holder."))
	billing_data = _billing(billing, offer.get("free"))
	result = ticketing.register_attendees(item.name, main, attends=cint(attends), companions=others,
		billing_data=billing_data, source="Website", lang=lang,
		expected_total=None if offer.get("free") or expected_total in (None, "") else expected_total,
		hold_id=_hold_id(hold_id, required=False))
	clear_section("events")
	return {"ok": True, "reference": result["reference"], "reference_doctype": result["reference_doctype"],
		"free": bool(offer.get("free")), "tickets_to": result["tickets_to"], "token": result["consent_token"]}


HOLD_ID = re.compile(r"[A-Za-z0-9-]{8,64}")
INTEREST = {"yes": "going_count", "maybe": "maybe_count", "no": "not_going_count"}
VOTER_ID = re.compile(r"[A-Za-z0-9-]{32,64}")


def _hold_id(value, required=True):
	value = (value or "").strip()
	if not value and not required:
		return None
	if not HOLD_ID.fullmatch(value):
		frappe.throw(_("Invalid request."))
	return value


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=60, seconds=60 * 60)
def hold(event, lang, hold_id, qty=1):
	"""Reserve seats and their price for 20 minutes while the visitor fills in the order (renewed per call)."""
	lang = _lang(lang)
	item = _event(event, lang)
	limit = cint((item.data.get("offer") or {}).get("max_per_order")) or MAX_ATTENDEES_PER_ORDER
	qty = min(max(1, cint(qty)), max(limit, 1))
	return ticketing.hold_seats(frappe.get_doc("Marketing Content", item.name), _hold_id(hold_id), qty)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=60 * 60)
def interest(event, lang, response, voter=None, previous=None, website=None):
	"""Anonymous Yes / Maybe / No: counts only, no personal data (gauges interest before tickets are sold).

	``voter``: a random id the browser keeps. The server stores each voter's current answer and only ever takes
	back that stored answer, never one the browser names: ``previous`` is ignored (phamos/phamos#1703).
	"""
	if website:
		return {"ok": True}
	item = _event(event, _lang(lang))
	if response not in INTEREST or not VOTER_ID.fullmatch((voter or "").strip()):
		frappe.throw(_("Invalid request."))
	stored = _swap_interest(item, voter.strip(), response)
	if stored in INTEREST and stored != response:
		field = INTEREST[stored]
		frappe.db.sql(f"update `tabMarketing Content` set `{field}` = greatest(0, coalesce(`{field}`, 0) - 1) where name = %s",
			item.name)
	if stored != response:
		field = INTEREST[response]
		frappe.db.sql(f"update `tabMarketing Content` set `{field}` = coalesce(`{field}`, 0) + 1 where name = %s", item.name)
	clear_section("events")
	counts = frappe.db.get_value("Marketing Content", item.name, list(INTEREST.values()), as_dict=True)
	return {"ok": True, "counts": {key: cint(counts[field]) for key, field in INTEREST.items()}}


def _interest_key(event, voter):
	"""Redis key of one voter's answer: a hash of the browser's id, never the id itself."""
	digest = hashlib.sha256(f"{frappe.local.site}|{voter}".encode()).hexdigest()[:32]
	return frappe.cache.make_key(f"event_interest:{event}:{digest}")


def _swap_interest(item, voter, response):
	"""Store ``response`` as the voter's answer and return the one stored before (or None), in one atomic
	step: two clicks at the same moment must not both take back the same old answer."""
	ends_on, starts_on = frappe.db.get_value("Marketing Content", item.name, ["ends_on", "starts_on"])
	end = get_datetime(ends_on or starts_on) if (ends_on or starts_on) else None
	# Kept until 30 days after the event (a year for events without a date), then the answer is forgotten.
	keep = (end + timedelta(days=30) - now_datetime()) if end else timedelta(days=365)
	seconds = max(int(keep.total_seconds()), 24 * 60 * 60)
	old = frappe.cache.set(_interest_key(item.name, voter), response, ex=seconds, get=True)
	return old.decode() if isinstance(old, bytes) else old


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60 * 60)
def save_consents(event, lang, reference, token, consents=None, website=None):
	"""The three optional questions after the order, signed with the token the order returned."""
	if website:
		return {"ok": True}
	lang = _lang(lang)
	item = _event(event, lang)
	reference = (reference or "").strip()
	if not ticketing.verify_consent_token(reference, token) or not frappe.db.exists("Attendee",
			{"event": item.name, "order_reference": reference}):
		frappe.throw(_("This link has expired. You can still subscribe on the event page."), frappe.PermissionError)
	values = _json(consents, {})
	values = {key: cint(values.get(key)) for key in ("newsletter", "attendee_contact", "public_listing")}
	email = ticketing.save_consents(reference, values, event=item.name)
	status = "saved"
	if values["newsletter"] and email and item.data.get("has_newsletter"):
		status = _start_double_opt_in(email, item.name)
	return {"ok": True, "status": status}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60 * 60)
def subscribe(event, lang, email, privacy_consent=None, website=None):
	if website:
		return {"ok": True}
	lang = _lang(lang)
	item = _event(event, lang)
	if not item.data.get("has_newsletter"):
		frappe.throw(_("This event has no updates by email."))
	if not cint(privacy_consent):
		frappe.throw(_("Please agree that we store your email address for these updates."))
	email = normalize_email(email)
	return {"ok": True, "status": _start_double_opt_in(email, item.name)}


def _start_double_opt_in(email, event_name):
	"""Frappe's standard double opt-in: a signed confirmation link; the address joins the Email Group only
	after it was confirmed. The group is read here, never taken from the request.

	Frappe's ``subscribe`` is called unwrapped: its own ``@rate_limit`` would count on this request's key a
	second time.
	"""
	from frappe.email.doctype.newsletter.newsletter import subscribe as frappe_subscribe

	group = frappe.db.get_value("Marketing Content", event_name, "email_group")
	if not group:
		return "no_group"
	# The same answer for a member and a new address, and nothing is sent to a member: a stranger must not
	# be able to find out who receives the updates (phamos/phamos#1702).
	if not frappe.db.exists("Email Group Member", {"email_group": group, "email": email, "unsubscribed": 0}):
		getattr(frappe_subscribe, "__wrapped__", frappe_subscribe)(email, group)
	return "confirmation_sent"


@frappe.whitelist(allow_guest=True, methods=["GET"])
def ics(event, lang=DEFAULT_LANGUAGE):
	lang = _lang(lang)
	item = _event(event, lang)
	if not item.data.get("ics"):
		frappe.throw(_("This event has no date yet."), frappe.DoesNotExistError)
	frappe.response.update({
		"type": "download",
		"filename": f"{item.slug}.ics",
		"filecontent": build_ics(item),
		"content_type": "text/calendar; charset=utf-8",
		"display_content_as": "attachment",
	})


MAX_REMINDERS = 3


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=30, seconds=60 * 60)
def reminders(event, lang=DEFAULT_LANGUAGE, at=None, tz=None):
	""""Create reminder": a calendar file with one short entry (with an alarm) per chosen date, up to three.
	``at`` is a comma-separated list of local "YYYY-MM-DDTHH:MM" values in the visitor's time zone ``tz``."""
	lang = _lang(lang)
	item = _event(event, lang)
	if not item.data.get("ics"):
		frappe.throw(_("This event has no date yet."), frappe.DoesNotExistError)
	moments = parse_reminders(at, tz)
	if not moments:
		frappe.throw(_("Please pick at least one date before the event."))
	frappe.response.update({
		"type": "download",
		"filename": f"{item.slug}-{_('reminder')}.ics",
		"filecontent": build_reminders_ics(item, moments),
		"content_type": "text/calendar; charset=utf-8",
		"display_content_as": "attachment",
	})


def parse_reminders(at, tz=None):
	"""Up to three aware datetimes from local values; unknown time zones fall back to the site's."""
	import pytz

	try:
		zone = pytz.timezone(tz) if tz else pytz.timezone(get_system_timezone())
	except pytz.UnknownTimeZoneError:
		zone = pytz.timezone(get_system_timezone())
	now = datetime.now(timezone.utc)
	moments = []
	for raw in str(at or "").split(",")[: MAX_REMINDERS * 2]:
		raw = raw.strip()
		if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?", raw):
			continue
		try:
			moment = zone.localize(get_datetime(raw.replace("T", " ")))
		except Exception:
			continue
		if moment > now and moment not in moments:
			moments.append(moment)
	return sorted(moments)[:MAX_REMINDERS]


def build_reminders_ics(item, moments):
	import pytz
	from icalendar import Alarm, Calendar, Event

	site_tz = pytz.timezone(get_system_timezone())
	when = item.data.get("when") or {}
	cal = Calendar()
	cal.add("prodid", "-//phamos//Events//DE")
	cal.add("version", "2.0")
	cal.add("method", "PUBLISH")
	for i, moment in enumerate(moments, 1):
		entry = Event()
		entry.add("uid", f"{item.name}-reminder-{moment.astimezone(pytz.utc):%Y%m%dT%H%M}@phamos.eu")
		entry.add("dtstamp", site_tz.localize(now_datetime()).astimezone(pytz.utc))
		# In UTC: no VTIMEZONE needed, every calendar app reads it the same way.
		entry.add("dtstart", moment.astimezone(pytz.utc))
		entry.add("dtend", moment.astimezone(pytz.utc) + timedelta(minutes=15))
		entry.add("summary", _("Reminder: {0}").format(item.title))
		entry.add("description", "\n\n".join(filter(None, [when.get("line"), get_url(item.url)])))
		entry.add("url", get_url(item.url))
		entry.add("transp", "TRANSPARENT")  # a reminder, not a meeting: does not block the calendar
		alarm = Alarm()
		alarm.add("action", "DISPLAY")
		alarm.add("description", _("Reminder: {0}").format(item.title))
		alarm.add("trigger", timedelta(0))
		entry.add_component(alarm)
		cal.add_component(entry)
	return cal.to_ical()


def build_ics(item, for_attendee=False):
	"""A calendar entry (METHOD:PUBLISH): no organizer, no attendees. ``LOCATION`` is the venue's address
	(with ``GEO`` when the pin is set) or, for an online event, "Online"; the meeting link itself only goes
	into the file attached to a ticket or order email (``for_attendee``)."""
	import pytz
	from icalendar import Calendar, Event

	from phamos.marketing.location import address_line

	record = frappe.db.get_value("Marketing Content", item.name, ["starts_on", "ends_on", "location"], as_dict=True)
	tz = pytz.timezone(get_system_timezone())
	start = tz.localize(get_datetime(record.starts_on))
	end = tz.localize(get_datetime(record.ends_on)) if record.ends_on else start + timedelta(hours=1)

	cal = Calendar()
	cal.add("prodid", "-//phamos//Events//DE")
	cal.add("version", "2.0")
	cal.add("method", "PUBLISH")
	entry = Event()
	entry.add("uid", f"{item.name}@phamos.eu")
	entry.add("dtstamp", tz.localize(now_datetime()).astimezone(pytz.utc))
	entry.add("dtstart", start)
	entry.add("dtend", end)
	entry.add("summary", item.title)
	d = item.data
	link = record.location if d.get("online") and for_attendee else None
	where = link or (_("Online") if d.get("online") else address_line(d))
	if where:
		entry.add("location", where)
	if d.get("latitude") is not None and d.get("longitude") is not None:
		entry.add("geo", (d["latitude"], d["longitude"]))
	entry.add("description", "\n\n".join(filter(None, [item.summary,
		_("Join online: {0}").format(link) if link else None, get_url(item.url)])))
	entry.add("url", get_url(item.url))
	cal.add_component(entry)
	return cal.to_ical()
