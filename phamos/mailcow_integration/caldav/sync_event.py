'''
EVENT Handlers 
(ERPNext --> VEVENT)

'''


from __future__ import annotations
import frappe
import requests
from datetime import datetime
import pytz
from email.utils import getaddresses
from datetime import datetime, timedelta, date
from .client import put_ics, delete_ics, organizer_email, dav_password
from .ics import vevent
from ..utils import get_site_timezone
from dateutil.rrule import rrulestr



def _uid_from_description_marker(description: str | None) -> str | None:
	"""Extract Mailcow UID marker used by hybrid flow, if present."""
	desc = description or ""
	marker = "[MAILCOW-UID: "
	idx = desc.find(marker)
	if idx < 0:
		return None
	uid = desc[idx + len(marker):].split("]")[0].strip()
	return uid or None


def _uid_belongs_to_other_event(uid: str | None, current_event_name: str | None) -> bool:
	"""True when UID is already linked to another Event record."""
	uid = (uid or "").strip()
	if not uid:
		return False

	filters = {"custom_mailcow_uid": uid}
	if current_event_name:
		filters["name"] = ["!=", current_event_name]

	other = frappe.db.get_value("Event", filters, "name")
	return bool(other)


def _resolve_sync_uid(doc) -> str:
	"""Choose a stable UID while preventing duplicate records from reusing another Event UID."""
	current_name = doc.get("name") or None

	stored_uid = (doc.get("custom_mailcow_uid") or "").strip()
	if stored_uid and not _uid_belongs_to_other_event(stored_uid, current_name):
		return stored_uid

	marker_uid = _uid_from_description_marker(doc.get("description"))
	if marker_uid and not _uid_belongs_to_other_event(marker_uid, current_name):
		return marker_uid

	# Fallback for duplicates/new docs: use this Event's own identity.
	return doc.name


def _get_linked_email(doctype: str | None, docname: str | None) -> str | None:
	"""Resolve an email for a linked participant reference."""
	if not (doctype and docname):
		return None

	if doctype == "User":
		return frappe.db.get_value("User", docname, "email")

	if doctype == "Lead":
		return (
			frappe.db.get_value("Lead", docname, "email_id")
			or frappe.db.get_value("Lead", docname, "email")
			or frappe.db.get_value("Lead", docname, "lead_email")
		)

	if doctype == "Contact":
		# Contact email is usually in child table `Contact Email`; fall back to direct field if present.
		email = frappe.db.sql(
			"""
			SELECT ce.email_id
			FROM `tabContact Email` ce
			WHERE ce.parent = %s
			ORDER BY ce.is_primary DESC, ce.idx ASC
			LIMIT 1
			""",
			(docname,),
			as_dict=False,
		)
		if email and email[0] and email[0][0]:
			return email[0][0]
		return frappe.db.get_value("Contact", docname, "email_id")

	# Best-effort fallback for doctypes that expose an email_id field.
	try:
		meta = frappe.get_meta(doctype)
		if meta.has_field("email_id"):
			return frappe.db.get_value(doctype, docname, "email_id")
	except Exception:
		pass

	return None


def _collect_event_participant_emails(doc) -> list[str]:
	"""Collect attendee emails from Event Participants rows."""
	emails: list[str] = []
	for row in (doc.get("event_participants") or []):
		candidate = None

		# If customizations added a direct email field on child table, prefer it.
		for fieldname in ("email", "email_id"):
			val = (row.get(fieldname) or "").strip()
			if val:
				candidate = val
				break

		if not candidate:
			candidate = _get_linked_email(row.get("reference_doctype"), row.get("reference_docname"))

		if not candidate:
			continue

		for _, addr in getaddresses([candidate]):
			if addr:
				emails.append(addr)

	# Deduplicate while preserving order.
	seen = set()
	uniq = []
	for e in emails:
		k = e.lower()
		if k in seen:
			continue
		seen.add(k)
		uniq.append(e)
	return uniq


def _collect_event_participant_roles(doc) -> dict[str, str]:
	"""Build attendee role map from Event Participants custom_participation."""
	roles: dict[str, str] = {}

	for row in (doc.get("event_participants") or []):
		candidate = None

		for fieldname in ("email", "email_id"):
			val = (row.get(fieldname) or "").strip()
			if val:
				candidate = val
				break

		if not candidate:
			candidate = _get_linked_email(row.get("reference_doctype"), row.get("reference_docname"))

		if not candidate:
			continue

		parsed = getaddresses([candidate])
		if not parsed:
			continue

		_, addr = parsed[0]
		if not addr:
			continue

		participation = (row.get("custom_participation") or "Optional").strip().lower()
		role = "REQ-PARTICIPANT" if participation == "required" else "OPT-PARTICIPANT"
		roles[addr.lower()] = role

	return roles


def _merge_attendees(existing_csv: str, new_emails: list[str]) -> str:
	"""Merge comma-separated attendees with new emails without duplicates."""
	merged: list[str] = []
	seen = set()

	for _, addr in getaddresses([existing_csv or ""]):
		if not addr:
			continue
		k = addr.lower()
		if k in seen:
			continue
		seen.add(k)
		merged.append(addr)

	for addr in (new_emails or []):
		k = addr.lower()
		if k in seen:
			continue
		seen.add(k)
		merged.append(addr)

	return ", ".join(merged)


def _event_location(doc) -> str:
	"""Get Event location from the standard Event field."""
	return (doc.get("location") or "").strip()


def _set_event_location(doc, value: str):
	"""Set Event location on the standard Event field."""
	meta = frappe.get_meta(doc.doctype)
	if meta.has_field("location"):
		doc.location = value


def _event_recurrence_rule(doc) -> str | None:
	"""Map Event repeat fields to RFC5545 RRULE for Mailcow sync."""
	if not doc.get("repeat_this_event"):
		return None

	repeat_on = (doc.get("repeat_on") or "").strip().lower()
	freq = {
		"daily": "DAILY",
		"weekly": "WEEKLY",
		"monthly": "MONTHLY",
		"yearly": "YEARLY",
	}.get(repeat_on)
	if not freq:
		return None

	parts: list[str] = [f"FREQ={freq}"]

	if freq == "WEEKLY":
		weekday_flags = [
			("monday", "MO"),
			("tuesday", "TU"),
			("wednesday", "WE"),
			("thursday", "TH"),
			("friday", "FR"),
			("saturday", "SA"),
			("sunday", "SU"),
		]
		selected_days = [abbr for fieldname, abbr in weekday_flags if doc.get(fieldname)]

		# Fallback for old data/UI states where no weekday checkbox is set.
		if not selected_days and doc.get("starts_on"):
			try:
				weekday = get_datetime(doc.get("starts_on")).weekday()
				selected_days = [["MO", "TU", "WE", "TH", "FR", "SA", "SU"][weekday]]
			except Exception:
				selected_days = []

		if selected_days:
			parts.append(f"BYDAY={','.join(selected_days)}")

	if doc.get("repeat_till"):
		try:
			until_date = get_datetime(doc.get("repeat_till"))
			parts.append(f"UNTIL={until_date.strftime('%Y%m%d')}T235959Z")
		except Exception:
			pass

	return ";".join(parts)

def on_upsert(doc, method=None):
	# auto_sync = frappe.db.get_value("Mailcow Settings", "auto_sync_events")

	try:
		sync_uid = _resolve_sync_uid(doc)

		# bump sequence to force client refresh
		seq = int(doc.get("custom_mailcow_seq") or 0) + 1
		doc.db_set("custom_mailcow_seq", seq, notify=False)

		# Extract attendees from custom fields if available
		attendees_to = doc.get("custom_attendees_to") or ""
		attendees_cc = doc.get("custom_attendees_cc") or ""
		attendees_bcc = doc.get("custom_attendees_bcc") or ""
		participant_emails = _collect_event_participant_emails(doc)
		participant_roles = _collect_event_participant_roles(doc)
		attendees_to = _merge_attendees(attendees_to, participant_emails)
		
		# Use the standard Event.location field.
		location = _event_location(doc)
		recurrence_rule = _event_recurrence_rule(doc)

		ics = vevent(
			uid=sync_uid,
			seq=seq,
			subject=doc.subject,
			starts_on=doc.starts_on,
			ends_on=doc.ends_on,
			description=doc.description or "",
			location=location,
			attendees_to=attendees_to,
			attendees_cc=attendees_cc,
			attendees_bcc=attendees_bcc,
			attendee_role_map=participant_roles,
			recurrence_rule=recurrence_rule,
		)
		put_ics(sync_uid, ics, acting_user_id=doc.owner)
		doc.db_set("custom_mailcow_uid", sync_uid, notify=False)
		doc.db_set("custom_mailcow_synched", 1, notify=False)
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Event CalDAV Sync Error")

def on_delete(doc, method=None):
	try:
		uid = (doc.get("custom_mailcow_uid") or "").strip() or _uid_from_description_marker(doc.get("description"))
		if uid and _uid_belongs_to_other_event(uid, doc.get("name")):
			# Safety: don't delete a calendar object that is still referenced by another Event.
			return

		delete_ics(uid or doc.name)
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
				_set_event_location(doc, loc)
				doc.custom_mailcow_etag = etag
				doc.save()
			else:
				event_payload = {
					"doctype": "Event",
					"subject": summary,
					"starts_on": dtstart_db,
					"ends_on": dtend_db,
					"description": desc,
					"custom_mailcow_uid": uid,
					"custom_mailcow_etag": etag,
					"owner": owner,
					"event_type": "Private",
					"custom_mailcow_synched": 1,
				}
				event_meta = frappe.get_meta("Event")
				if event_meta.has_field("location"):
					event_payload["location"] = loc
				doc = frappe.get_doc(event_payload)
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


@frappe.whitelist()
def pull_event_slots(start: str, end: str) -> list[dict]:
	"""
	Read events from Mailcow/SOGo CalDAV for the current user.

	- Does NOT create/update ERPNext Events.
	- Supports normal VEVENTs.
	- Supports recurring VEVENTs.
	- Supports RRULE with DAILY/WEEKLY/MONTHLY/YEARLY.
	- Supports COUNT and UNTIL.
	- Preserves the original event timezone while expanding recurrence.
	- Converts returned slots to UTC ISO strings.
	"""

	import datetime
	from datetime import timedelta

	import dateutil.parser
	import requests
	import pytz

	from icalendar import Calendar
	from dateutil.rrule import rrulestr
	from xml.etree import ElementTree as ET

	from frappe.utils import get_datetime

	# CONFIG

	s = frappe.get_single("Mailcow Settings")

	# Use the current user's organizer email.
	EMAIL = organizer_email()

	if not EMAIL:
		frappe.throw(
			"Could not determine organizer email."
		)

	# PASSWORD

	pw = dav_password(EMAIL)

	if not pw:
		frappe.throw(
			f"Missing DAV password for {EMAIL}"
		)

	# REQUEST RANGE

	start_dt = dateutil.parser.isoparse(start)
	end_dt = dateutil.parser.isoparse(end)

	if start_dt.tzinfo is None:
		start_dt = start_dt.replace(
			tzinfo=pytz.UTC
		)

	if end_dt.tzinfo is None:
		end_dt = end_dt.replace(
			tzinfo=pytz.UTC
		)

	# Maximum 90 days
	if (end_dt - start_dt).days > 90:
		frappe.throw(
			"Date range too large; max 90 days"
		)

	# UTC HELPER

	def to_utc(dt):
		"""
		Convert datetime to timezone-aware UTC datetime.
		"""

		if dt is None:
			return None

		if (
			isinstance(dt, datetime.date)
			and not isinstance(dt, datetime.datetime)
		):
			dt = datetime.datetime.combine(
				dt,
				datetime.time.min
			)

		if dt.tzinfo is None:
			site_timezone = get_site_timezone()
			site_tz = pytz.timezone(
				site_timezone
			)

			dt = site_tz.localize(dt)

		return dt.astimezone(pytz.UTC)

	# REQUEST RANGE IN UTC

	start_dt_utc = to_utc(start_dt)
	end_dt_utc = to_utc(end_dt)


	# OVERLAP CHECK

	def overlaps(event_start, event_end):
		return (
			event_end >= start_dt_utc
			and event_start <= end_dt_utc
		)

	# RRULE PARSER

	def parse_rrule(component, dtstart):
		"""
		Convert iCalendar RRULE into dateutil rrule.

		DTSTART remains in the original event timezone.
		"""

		rrule_prop = component.get("RRULE")

		if not rrule_prop:
			return None

		try:

			rule_string = (
				rrule_prop
				.to_ical()
				.decode()
			)


			return rrulestr(
				rule_string,
				dtstart=dtstart,
			)

		except Exception:

			frappe.log_error(
				frappe.get_traceback(),
				"Mailcow CalDAV RRULE Parse Error"
			)

			return None

	# PARSE ONE VCALENDAR

	def collect_slots_from_ical(cal_raw):

		parsed_slots = []

		if not cal_raw:
			return parsed_slots

		try:

			cal = Calendar.from_ical(
				cal_raw
			)

		except Exception:

			frappe.log_error(
				frappe.get_traceback(),
				"Mailcow CalDAV iCalendar Parse Error"
			)

			return parsed_slots

		# COLLECT EXDATE VALUES

		exdates = set()

		for component in cal.walk():

			if component.name != "VEVENT":
				continue

			exdate_prop = component.get(
				"EXDATE"
			)

			if not exdate_prop:
				continue

			try:

				values = []

				if isinstance(
					exdate_prop,
					list
				):

					for item in exdate_prop:
						values.extend(
							item.dts
						)

				else:

					values.extend(
						exdate_prop.dts
					)

				for item in values:

					exdate = item.dt

					if (
						isinstance(
							exdate,
							datetime.date
						)
						and not isinstance(
							exdate,
							datetime.datetime
						)
					):

						exdate = (
							datetime.datetime.combine(
								exdate,
								datetime.time.min
							)
						)

					if exdate.tzinfo is None:

						site_timezone = (
							get_site_timezone()
						)

						site_tz = pytz.timezone(
							site_timezone
						)

						exdate = site_tz.localize(
							exdate
						)

					exdates.add(
						exdate.astimezone(
							pytz.UTC
						)
					)

			except Exception:
				pass

		# PROCESS VEVENTS

		for component in cal.walk():

			if component.name != "VEVENT":
				continue

			uid = str(
				component.get("UID") or ""
			)

			summary = str(
				component.get("SUMMARY") or ""
			)

			desc = str(
				component.get("DESCRIPTION") or ""
			)

			loc = str(
				component.get("LOCATION") or ""
			)

			# DTSTART

			dtstart_prop = component.get(
				"DTSTART"
			)

			if not dtstart_prop:
				continue

			raw_start = dtstart_prop.dt

			if (
				isinstance(
					raw_start,
					datetime.date
				)
				and not isinstance(
					raw_start,
					datetime.datetime
				)
			):

				raw_start = (
					datetime.datetime.combine(
						raw_start,
						datetime.time.min
					)
				)

			# IMPORTANT:
			# Keep original timezone.
			dtstart = get_datetime(
				raw_start
			)

			if dtstart.tzinfo is None:

				site_timezone = (
					get_site_timezone()
				)

				site_tz = pytz.timezone(
					site_timezone
				)

				dtstart = site_tz.localize(
					dtstart
				)

			# DTEND / DURATION

			dtend_prop = component.get(
				"DTEND"
			)

			if dtend_prop:

				raw_end = dtend_prop.dt

				if (
					isinstance(
						raw_end,
						datetime.date
					)
					and not isinstance(
						raw_end,
						datetime.datetime
					)
				):

					raw_end = (
						datetime.datetime.combine(
							raw_end,
							datetime.time.min
						)
					)

				dtend = get_datetime(
					raw_end
				)

				if dtend.tzinfo is None:

					site_timezone = (
						get_site_timezone()
					)

					site_tz = pytz.timezone(
						site_timezone
					)

					dtend = site_tz.localize(
						dtend
					)

				duration = (
					dtend - dtstart
				)

			elif component.get(
				"DURATION"
			):

				duration = component.get(
					"DURATION"
				).dt

				dtend = (
					dtstart + duration
				)

			else:

				duration = timedelta(0)

				dtend = dtstart

			# UTC BASE TIMES

			dtstart_utc = to_utc(
				dtstart
			)

			dtend_utc = to_utc(
				dtend
			)

			# RECURRENCE ID

			recurrence_id_prop = (
				component.get(
					"RECURRENCE-ID"
				)
			)

			# NON-RECURRING EVENT

			rrule_prop = component.get(
				"RRULE"
			)

			if not rrule_prop:

				if not overlaps(
					dtstart_utc,
					dtend_utc
				):
					continue

				parsed_slots.append({

					"uid": uid,

					"subject": summary,

					"start":
						dtstart_utc.isoformat(),

					"end":
						dtend_utc.isoformat(),

					"duration_minutes":
						int(
							duration.total_seconds()
							/ 60
						),

					"slot": {
						"start":
							dtstart_utc.isoformat(),

						"end":
							dtend_utc.isoformat(),
					},

					"description": desc,

					"location": loc,
				})

				continue

			# RECURRING EVENT

			rule = parse_rrule(
				component,
				dtstart
			)

			if not rule:
				continue

			# IMPORTANT:
			# Expand in the event's original timezone.
			event_tz = dtstart.tzinfo

			range_start_local = (
				start_dt_utc.astimezone(
					event_tz
				)
				- duration
			)

			range_end_local = (
				end_dt_utc.astimezone(
					event_tz
				)
			)

			try:

				occurrences = rule.between(
					range_start_local,
					range_end_local,
					inc=True,
				)

			except Exception:

				frappe.log_error(
					frappe.get_traceback(),
					"Mailcow CalDAV Recurrence Expansion Error"
				)

				continue

			# OCCURRENCES

			for occurrence in occurrences:

				if occurrence.tzinfo is None:

					occurrence = (
						event_tz.localize(
							occurrence
						)
					)

				occurrence_utc = (
					occurrence.astimezone(
						pytz.UTC
					)
				)

				occurrence_end_utc = (
					occurrence_utc
					+ duration
				)

				# EXDATE

				if occurrence_utc in exdates:
					continue

				# RANGE

				if not overlaps(
					occurrence_utc,
					occurrence_end_utc
				):
					continue

				parsed_slots.append({

					"uid": uid,

					"subject": summary,

					"start":
						occurrence_utc.isoformat(),

					"end":
						occurrence_end_utc.isoformat(),

					"duration_minutes":
						int(
							duration.total_seconds()
							/ 60
						),

					"slot": {
						"start":
							occurrence_utc.isoformat(),

						"end":
							occurrence_end_utc.isoformat(),
					},

					"description": desc,

					"location": loc,
				})

		return parsed_slots

	# CALDAV URL

	url = (
		f"{s.base_url.rstrip('/')}"
		f"/SOGo/dav/{EMAIL}/Calendar/personal/"
	)

	# CALDAV REPORT RANGE

	start_utc_str = (
		start_dt_utc.strftime(
			"%Y%m%dT%H%M%SZ"
		)
	)

	end_utc_str = (
		end_dt_utc.strftime(
			"%Y%m%dT%H%M%SZ"
		)
	)

	# IMPORTANT:
	# Keep the time-range filter.
	#
	# DO NOT replace this with PROPFIND/full-calendar GET,
	# otherwise SOGo can return the entire calendar.

	query_xml = f"""<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query
	xmlns:D="DAV:"
	xmlns:C="urn:ietf:params:xml:ns:caldav">

	<D:prop>
		<D:getetag/>
		<C:calendar-data/>
	</D:prop>

	<C:filter>
		<C:comp-filter name="VCALENDAR">
			<C:comp-filter name="VEVENT">
				<C:time-range
					start="{start_utc_str}"
					end="{end_utc_str}"/>
			</C:comp-filter>
		</C:comp-filter>
	</C:filter>

</C:calendar-query>"""

	# CALDAV REPORT

	try:

		r = requests.request(
			"REPORT",
			url,
			auth=(
				EMAIL,
				pw
			),
			headers={
				"Depth": "1",
				"Content-Type":
					"application/xml; charset=utf-8",
			},
			data=query_xml.encode(
				"utf-8"
			),
			timeout=30,
		)

	except Exception:

		frappe.log_error(
			frappe.get_traceback(),
			"Mailcow CalDAV REPORT Request Error"
		)

		frappe.throw(
			"Could not connect to Mailcow CalDAV."
		)

	# RESPONSE

	if r.status_code != 207:

		frappe.log_error(
			r.text[:5000],
			"Mailcow CalDAV REPORT Failed"
		)

		frappe.throw(
			"Mailcow calendar REPORT failed: "
			f"{r.status_code}"
		)

	# XML

	ns = {
		"D": "DAV:",
		"C": "urn:ietf:params:xml:ns:caldav",
	}

	try:

		root = ET.fromstring(
			r.content
		)

	except Exception:

		frappe.log_error(
			frappe.get_traceback(),
			"Mailcow CalDAV XML Parse Error"
		)

		frappe.throw(
			"Invalid XML returned by Mailcow."
		)

	responses = root.findall(
		"D:response",
		ns
	)

	# COLLECT

	slots = []

	for resp in responses:

		calendar_data_el = resp.find(
			"D:propstat/D:prop/C:calendar-data",
			ns
		)

		if (
			calendar_data_el is None
			or not calendar_data_el.text
		):
			continue

		try:

			new_slots = (
				collect_slots_from_ical(
					calendar_data_el.text
				)
			)

			slots.extend(
				new_slots
			)

		except Exception:

			frappe.log_error(
				frappe.get_traceback(),
				"Mailcow Calendar Event Parsing Error"
			)

	# DEDUPLICATE

	unique_slots = []

	seen = set()

	for slot in slots:

		key = (
			slot.get("uid"),
			slot.get("start"),
			slot.get("end"),
		)

		if key in seen:
			continue

		seen.add(key)

		unique_slots.append(
			slot
		)

	# SORT

	unique_slots.sort(
		key=lambda item: (
			item.get("start") or "",
			item.get("end") or "",
		)
	)

	return unique_slots
