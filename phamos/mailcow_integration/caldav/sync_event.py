'''
EVENT Handlers 
(ERPNext --> VEVENT)

'''


from __future__ import annotations
import frappe
import requests
from datetime import datetime
import pytz
from .client import put_ics, delete_ics, organizer_email, dav_password
from .ics import vevent
from ..utils import get_site_timezone

def on_upsert(doc, method=None):
	# auto_sync = frappe.db.get_value("Mailcow Settings", "auto_sync_events")

	try:
		# bump sequence to force client refresh
		seq = int(doc.get("custom_mailcow_seq") or 0) + 1
		doc.db_set("custom_mailcow_seq", seq, notify=False)

		# Extract attendees from custom fields if available
		attendees_to = doc.get("custom_attendees_to") or ""
		attendees_cc = doc.get("custom_attendees_cc") or ""
		attendees_bcc = doc.get("custom_attendees_bcc") or ""
		
		# Get location from custom field (Jitsi link for hybrid meetings)
		location = doc.get("custom_location") or ""

		ics = vevent(
			uid=doc.name,
			seq=seq,
			subject=doc.subject,
			starts_on=doc.starts_on,
			ends_on=doc.ends_on,
			description=doc.description or "",
			location=location,
			attendees_to=attendees_to,
			attendees_cc=attendees_cc,
			attendees_bcc=attendees_bcc,
		)
		put_ics(doc.name, ics, acting_user_id=doc.owner)
		doc.db_set("custom_mailcow_uid", doc.name, notify=False)
		doc.db_set("custom_mailcow_synched", 1, notify=False)
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Event CalDAV Sync Error")

def on_delete(doc, method=None):
	try:
		delete_ics(doc.name)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Event CalDAV Delete Error")


@frappe.whitelist()
def manual_sync_event(event_name: str):
	"""Manually sync a single Event by name (docname)"""
	doc = frappe.get_doc("Event", event_name)
	on_upsert(doc)
	return {"status": "ok", "event": event_name}


@frappe.whitelist()
def pull_events(start: str, end: str) -> list[dict]:
	"""
	Fetch events from Mailcow to Events Doctype 
	for the current user between start and end (ISO strings)
	"""

	from frappe.utils import date_diff, get_datetime
	import dateutil.parser

	s = frappe.get_single("Mailcow Settings")

	owner = frappe.session.user
	if owner == "Administrator":
		frappe.throw("You're logged in as Administrator; cannot determine organizer email.")

	email = organizer_email()
	pw = dav_password(email)
	if not (email and pw):
		frappe.throw("Missing DAV credentials for organizer")

	start_dt = dateutil.parser.isoparse(start)
	end_dt = dateutil.parser.isoparse(end)
	if date_diff(end_dt, start_dt) > 90:
		frappe.throw("Date range too large; max 90 days")

	# Normalize all comparisons to UTC aware datetimes
	site_tz = pytz.timezone(get_site_timezone())
	def to_utc(dt: datetime):
		# If dt is date-only or naive, localize to site tz first
		if dt is None:
			return None
		if dt.tzinfo is None:
			dt = site_tz.localize(dt)
		return dt.astimezone(pytz.UTC)

	start_dt_utc = to_utc(start_dt)
	end_dt_utc = to_utc(end_dt)

	url = f"{s.base_url.rstrip('/')}/SOGo/dav/{email}/Calendar/personal/"
	r = requests.request("PROPFIND", url,
		auth=(email, pw),
		headers={"Depth": "1"},
		timeout=30
	)
	if r.status_code != 207:
		frappe.throw(f"SOGo PROPFIND failed: {r.status_code}: {r.text[:500]}")

	from xml.etree import ElementTree as ET
	ns = {"D": "DAV:", "C": "urn:ietf:params:xml:ns:caldav"}
	root = ET.fromstring(r.content)
	events = []
	for resp in root.findall("D:response", ns):
		href = resp.find("D:href", ns)
		if href is None or not href.text.endswith(".ics"):
			continue
		etag_el = resp.find("D:propstat/D:prop/D:getetag", ns)
		etag = etag_el.text if etag_el is not None else None

		# fetch the actual .ics
		caldav_url = url + href.text.split("/")[-1]
		r2 = requests.get(caldav_url,
			auth=(email, pw),
			timeout=30
		)
		if r2.status_code != 200:
			frappe.log_error(f"SOGo GET failed: {r2.status_code}: {r2.text[:500]}", "CalDAV GET")
			continue

		from icalendar import Calendar
		cal = Calendar.from_ical(r2.content)
		for component in cal.walk():
			if component.name != "VEVENT":
				continue
			uid = str(component.get("UID"))
			summary = str(component.get("SUMMARY"))
			desc = str(component.get("DESCRIPTION") or "")
			loc = str(component.get("LOCATION") or "")
			raw_start = component.get("DTSTART").dt
			raw_end = component.get("DTEND").dt
			dtstart = get_datetime(raw_start)
			dtend = get_datetime(raw_end)

			# Convert to UTC for comparison and normalize for DB storage (naive)
			dtstart_utc = to_utc(dtstart)
			dtend_utc = to_utc(dtend)
			dtstart_db = dtstart_utc.replace(tzinfo=None) if dtstart_utc else None
			dtend_db = dtend_utc.replace(tzinfo=None) if dtend_utc else None
			if (dtend_utc and dtend_utc < start_dt_utc) or (dtstart_utc and dtstart_utc > end_dt_utc):
				continue

			# Upsert Event
			existing = frappe.get_all("Event", filters={"custom_mailcow_uid": uid, "owner": owner}, fields=["name"], limit=1)
			if existing:
				doc = frappe.get_doc("Event", existing[0]["name"])
				doc.subject = summary
				doc.starts_on = dtstart_db
				doc.ends_on = dtend_db
				doc.description = desc
				doc.custom_location = loc
				doc.custom_mailcow_etag = etag
				doc.save()
			else:
				doc = frappe.get_doc({
					"doctype": "Event",
					"subject": summary,
					"starts_on": dtstart_db,
					"ends_on": dtend_db,
					"description": desc,
					"custom_location": loc,
					"custom_mailcow_uid": uid,
					"custom_mailcow_etag": etag,
					"owner": owner,
					"event_type": "Private",
					"custom_mailcow_synched": 1,
				})
				doc.insert()

			events.append({
				"uid": uid,
				"subject": summary,
				"starts_on": dtstart.isoformat(),
				"ends_on": dtend.isoformat(),
				"description": desc,
				"location": loc,
			})

	return events
	