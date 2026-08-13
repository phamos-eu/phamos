# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import add_to_date, getdate, nowdate

from phamos.mailcow_integration.caldav.sync_event import pull_event_slots as sync_pull_event_slots
from phamos.mailcow_integration.utils import get_site_timezone


WEEKDAYS = [
	"Monday",
	"Tuesday",
	"Wednesday",
	"Thursday",
	"Friday",
	"Saturday",
	"Sunday",
]

DEFAULT_TIME_FROM = "07:00"
DEFAULT_TIME_TO = "18:00"

OPTIONAL_SLOTS = [
	("Before Working Hours", "07:00", "08:00"),
	("Lunch Break", "12:00", "13:00"),
	("After Working Hours", "18:00", "19:00"),
]

STATUS_COLORS = {
	"Available": "#2EAF4A",
	"Booked": "#D94841",
	"Optional": "#E0A106",
}


# Keep Employee Availability focused on the employee's primary calendar.
INCLUDE_ALL_CALENDARS = True


def _run_as_user(user_id: str, fn, *args, **kwargs):
	current_user = frappe.session.user
	try:
		if user_id and current_user != user_id:
			frappe.set_user(user_id)
		return fn(*args, **kwargs)
	finally:
		if frappe.session.user != current_user:
			frappe.set_user(current_user)


def _fetch_mailcow_events_between(user_id: str, start_local, end_local, tz):
	import dateutil.parser

	if end_local <= start_local:
		frappe.throw(_("Time To must be after Time From."))

	start_utc = start_local.astimezone(timezone.utc)
	end_utc = end_local.astimezone(timezone.utc)

	try:
		synced_events = _run_as_user(
			user_id,
			sync_pull_event_slots,
			start_local.isoformat(),
			end_local.isoformat(),
		) or []
	except Exception:
		frappe.throw(_("Mailcow event pull failed. Please try again."))

	events = []
	for item in synced_events:
		start_raw = item.get("start") or item.get("starts_on")
		end_raw = item.get("end") or item.get("ends_on")
		if not start_raw or not end_raw:
			continue

		try:
			start_dt = dateutil.parser.isoparse(str(start_raw))
			end_dt = dateutil.parser.isoparse(str(end_raw))
		except Exception:
			start_dt = frappe.utils.get_datetime(start_raw)
			end_dt = frappe.utils.get_datetime(end_raw)
		if start_dt is None or end_dt is None:
			continue

		if start_dt.tzinfo is None:
			start_dt = tz.localize(start_dt)
		else:
			start_dt = start_dt.astimezone(tz)

		if end_dt.tzinfo is None:
			end_dt = tz.localize(end_dt)
		else:
			end_dt = end_dt.astimezone(tz)

		start_dt_utc = start_dt.astimezone(timezone.utc)
		end_dt_utc = end_dt.astimezone(timezone.utc)
		if end_dt_utc <= start_utc or start_dt_utc >= end_utc:
			continue

		clipped_start = max(start_dt_utc, start_utc)
		clipped_end = min(end_dt_utc, end_utc)
		if clipped_end <= clipped_start:
			continue

		events.append(
			{
				"uid": item.get("uid") or "",
				"title": item.get("subject") or "(No Title)",
				"description": item.get("description") or "",
				"location": item.get("location") or "",
				"start_utc": clipped_start,
				"end_utc": clipped_end,
			}
		)

	# Dedupe by UID/title/time and sort.
	unique = {}
	for ev in events:
		key = (
			ev.get("uid") or "",
			ev.get("title") or "",
			ev["start_utc"].isoformat(),
			ev["end_utc"].isoformat(),
		)
		if key not in unique:
			unique[key] = ev

	return sorted(unique.values(), key=lambda d: d["start_utc"])


def _fetch_mailcow_events_for_window(
	user_id: str,
	day,
	time_from: str,
	time_to: str,
	tz_name: str | None = None,
	include_all_calendars: bool = False,
):
	tz = _resolve_calendar_timezone(user_id, tz_name)
	start_t = datetime.strptime(time_from, "%H:%M").time()
	end_t = datetime.strptime(time_to, "%H:%M").time()

	start_local = tz.localize(datetime(day.year, day.month, day.day, start_t.hour, start_t.minute, 0))
	end_local = tz.localize(datetime(day.year, day.month, day.day, end_t.hour, end_t.minute, 0))
	events = _fetch_mailcow_events_between(user_id, start_local, end_local, tz)
	return events, tz


def _fetch_mailcow_events_for_range(
	user_id: str,
	from_date,
	to_date,
	time_from: str,
	time_to: str,
	tz_name: str | None = None,
	include_all_calendars: bool = False,
):
	tz = _resolve_calendar_timezone(user_id, tz_name)
	start_t = datetime.strptime(time_from, "%H:%M").time()
	end_t = datetime.strptime(time_to, "%H:%M").time()

	start_local = tz.localize(datetime(from_date.year, from_date.month, from_date.day, start_t.hour, start_t.minute, 0))
	end_local = tz.localize(datetime(to_date.year, to_date.month, to_date.day, end_t.hour, end_t.minute, 0))

	events = _fetch_mailcow_events_between(user_id, start_local, end_local, tz)
	return events, tz


@frappe.whitelist()
def pull_mailcow_events(
	employee: str,
	day: str,
	time_from: str = DEFAULT_TIME_FROM,
	time_to: str = DEFAULT_TIME_TO,
	duration: int = 60,
	tz_name: str | None = None,
	include_all_calendars: bool = False,
):
	"""Pull Mailcow VEVENTs for a specific day and time window with full details."""
	if not employee:
		frappe.throw(_("Employee is required."))
	if not day:
		frappe.throw(_("Day is required."))

	day_value = getdate(day)
	user_id, _ = _resolve_employee_calendar_user(employee)
	events, tz = _fetch_mailcow_events_for_window(
		user_id=user_id,
		day=day_value,
		time_from=time_from,
		time_to=time_to,
		tz_name=tz_name,
		include_all_calendars=bool(include_all_calendars),
	)

	rows = []
	for ev in events:
		start_local = ev["start_utc"].astimezone(tz)
		end_local = ev["end_utc"].astimezone(tz)
		rows.append(
			{
				"uid": ev.get("uid"),
				"title": ev.get("title"),
				"description": ev.get("description"),
				"location": ev.get("location"),
				"date": start_local.date().strftime("%Y-%m-%d"),
				"day": start_local.strftime("%A"),
				"start": start_local.strftime("%Y-%m-%d %H:%M:%S"),
				"end": end_local.strftime("%Y-%m-%d %H:%M:%S"),
				"from_time": start_local.strftime("%H:%M:%S"),
				"to_time": end_local.strftime("%H:%M:%S"),
				"duration_minutes": int((end_local - start_local).total_seconds() // 60),
			}
		)

	return {
		"employee": employee,
		"day": day_value.strftime("%Y-%m-%d"),
		"time_from": time_from,
		"time_to": time_to,
		"duration": int(duration),
		"timezone": str(tz),
		"events": rows,
	}


@frappe.whitelist()
def get_booked_slots_for_day(
	employee: str,
	day: str,
	duration: int = 60,
	time_from: str = DEFAULT_TIME_FROM,
	time_to: str = DEFAULT_TIME_TO,
	tz_name: str | None = None,
	include_all_calendars: bool = False,
):
	"""Return booked slots for a day with event title and details.

	Each event is split into slot rows using the requested duration (minutes).
	"""
	if not employee:
		frappe.throw(_("Employee is required."))
	if not day:
		frappe.throw(_("Day is required."))

	step_minutes = int(duration or 60)
	if step_minutes <= 0:
		frappe.throw(_("Duration must be greater than 0."))

	payload = pull_mailcow_events(
		employee=employee,
		day=day,
		time_from=time_from,
		time_to=time_to,
		duration=step_minutes,
		tz_name=tz_name,
		include_all_calendars=include_all_calendars,
	)

	booked_slots = []
	for ev in payload.get("events") or []:
		start_dt = datetime.strptime(ev["start"], "%Y-%m-%d %H:%M:%S")
		end_dt = datetime.strptime(ev["end"], "%Y-%m-%d %H:%M:%S")

		cursor = start_dt
		while cursor < end_dt:
			next_end = min(cursor + timedelta(minutes=step_minutes), end_dt)
			booked_slots.append(
				{
					"date": ev["date"],
					"day": ev["day"],
					"from_time": cursor.strftime("%H:%M:%S"),
					"to_time": next_end.strftime("%H:%M:%S"),
					"duration_minutes": int((next_end - cursor).total_seconds() // 60),
					"event_title": ev.get("title"),
					"event_description": ev.get("description"),
					"event_location": ev.get("location"),
					"event_uid": ev.get("uid"),
				}
			)
			cursor = next_end

	return {
		"employee": payload.get("employee"),
		"day": payload.get("day"),
		"time_from": payload.get("time_from"),
		"time_to": payload.get("time_to"),
		"duration": step_minutes,
		"timezone": payload.get("timezone"),
		"events": payload.get("events"),
		"booked_slots": booked_slots,
	}


class EmployeeAvailability(Document):
	def autoname(self):
		self._set_company()
		company_abbr = frappe.db.get_value("Company", self.company, "abbr") if self.company else None
		if not company_abbr:
			company_abbr = "EA"

		employee_key = self.employee or "EMP"
		name_key = f"{company_abbr}-.YYYY.-{employee_key}-.####"
		self.name = make_autoname(name_key)
		self.title_hour = self.name

	def before_insert(self):
		self._set_default_dates()
		self._set_company()

	def validate(self):
		self._set_default_dates()
		self._set_company()

		if self.from_date and self.to_date and getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("From Date cannot be after To Date."))

	def _set_default_dates(self):
		month_start, month_end = _get_current_month_bounds()
		if not self.from_date:
			self.from_date = month_start
		if not self.to_date:
			self.to_date = month_end

	def _set_company(self):
		if self.company:
			return

		if self.employee:
			employee_company = frappe.db.get_value("Employee", self.employee, "company")
			if employee_company:
				self.company = employee_company
				return

		self.company = _get_default_company()


def _get_current_month_bounds():
	today = getdate(nowdate())
	month_start = today.replace(day=1)
	month_end = getdate(add_to_date(month_start, months=1, days=-1))
	return month_start, month_end


def _get_default_company():
	try:
		from erpnext import get_default_company

		return get_default_company()
	except Exception:
		return None


def _resolve_employee_calendar_user(employee: str):
	user_id = frappe.db.get_value("Employee", employee, "user_id")
	if not user_id:
		frappe.throw(_("Employee {0} has no linked User.").format(frappe.bold(employee)))

	user_email = frappe.db.get_value("User", user_id, "email") or user_id
	if not user_email:
		frappe.throw(_("Unable to resolve email for User {0}.").format(frappe.bold(user_id)))

	if not frappe.db.exists("Mailcow DAV Password", {"user": user_email}):
		frappe.throw(
			_("No Mailcow DAV Password found for {0}. Please generate DAV password first.").format(
				frappe.bold(user_email)
			)
		)

	return user_id, user_email


def _merge_intervals(intervals):
	if not intervals:
		return []

	ordered = sorted(intervals, key=lambda item: item[0])
	merged = [ordered[0]]
	for start_dt, end_dt in ordered[1:]:
		last_start, last_end = merged[-1]
		if start_dt <= last_end:
			merged[-1] = (last_start, max(last_end, end_dt))
		else:
			merged.append((start_dt, end_dt))

	return merged


def _subtract_intervals(base_intervals, blocked_intervals):
	"""Subtract blocked intervals from base intervals and return remaining fragments."""
	if not base_intervals:
		return []
	if not blocked_intervals:
		return base_intervals

	blocked = _merge_intervals(blocked_intervals)
	result = []

	for base_start, base_end in base_intervals:
		fragments = [(base_start, base_end)]
		for block_start, block_end in blocked:
			next_fragments = []
			for frag_start, frag_end in fragments:
				if block_end <= frag_start or block_start >= frag_end:
					next_fragments.append((frag_start, frag_end))
					continue

				if block_start > frag_start:
					next_fragments.append((frag_start, min(block_start, frag_end)))
				if block_end < frag_end:
					next_fragments.append((max(block_end, frag_start), frag_end))

			fragments = next_fragments
			if not fragments:
				break

		result.extend(fragments)

	return result

def _resolve_calendar_timezone(user_id: str, tz_name: str | None = None):
	import pytz

	resolved_tz_name = tz_name or frappe.db.get_value("User", user_id, "time_zone") or get_site_timezone()
	try:
		return pytz.timezone(resolved_tz_name)
	except Exception:
		return pytz.timezone(get_site_timezone())


def _build_busy_slots_for_range(user_id: str, from_date, to_date, tz_name: str | None = None):
	events, tz = _fetch_mailcow_events_for_range(
		user_id=user_id,
		from_date=from_date,
		to_date=to_date,
		time_from="00:00",
		time_to="23:59",
		tz_name=tz_name,
		include_all_calendars=INCLUDE_ALL_CALENDARS,
	)
	busy_intervals = [(event["start_utc"], event["end_utc"]) for event in events]

	busy_intervals = _merge_intervals(busy_intervals)

	rows = []
	for start_utc, end_utc in busy_intervals:
		local_start = start_utc.astimezone(tz)
		local_end = end_utc.astimezone(tz)
		duration_seconds = int((local_end - local_start).total_seconds())
		if duration_seconds <= 0:
			continue

		rows.append(
			{
				"date": local_start.date(),
				"day": local_start.strftime("%A"),
				"duration": duration_seconds,
				"from_time": local_start.strftime("%H:%M:%S"),
				"to_time": local_end.strftime("%H:%M:%S"),
			}
		)

	return sorted(rows, key=lambda d: (d["date"], d["from_time"], d["to_time"]))


def _build_free_slots_for_range(
	user_id: str,
	from_date,
	to_date,
	tz_name: str | None = None,
	time_from: str = DEFAULT_TIME_FROM,
	time_to: str = DEFAULT_TIME_TO,
):
	tz = _resolve_calendar_timezone(user_id, tz_name)
	window_start = datetime.strptime(time_from, "%H:%M").time()
	window_end = datetime.strptime(time_to, "%H:%M").time()
	range_events, _ = _fetch_mailcow_events_for_range(
		user_id=user_id,
		from_date=from_date,
		to_date=to_date,
		time_from=time_from,
		time_to=time_to,
		tz_name=tz_name,
		include_all_calendars=INCLUDE_ALL_CALENDARS,
	)
	slots = []
	current_date = from_date
	while current_date <= to_date:
		start_local = tz.localize(
			datetime(
				current_date.year,
				current_date.month,
				current_date.day,
				window_start.hour,
				window_start.minute,
				0,
			)
		)
		end_local = tz.localize(
			datetime(
				current_date.year,
				current_date.month,
				current_date.day,
				window_end.hour,
				window_end.minute,
				0,
			)
		)

		if end_local <= start_local:
			current_date += timedelta(days=1)
			continue

		busy_local = []
		for event in range_events:
			event_start_local = event["start_utc"].astimezone(tz)
			event_end_local = event["end_utc"].astimezone(tz)
			clipped_start = max(event_start_local, start_local)
			clipped_end = min(event_end_local, end_local)
			if clipped_end > clipped_start:
				busy_local.append((clipped_start, clipped_end))

		busy_local = _merge_intervals(busy_local)
		free_local = []
		cursor = start_local
		for busy_start, busy_end in busy_local:
			if busy_end <= cursor or busy_start >= end_local:
				continue
			if busy_start > cursor:
				free_local.append((cursor, min(busy_start, end_local)))
			cursor = max(cursor, busy_end)
			if cursor >= end_local:
				break

		if cursor < end_local:
			free_local.append((cursor, end_local))

		for free_start_local, free_end_local in free_local:

			duration_seconds = int((free_end_local - free_start_local).total_seconds())

			if duration_seconds <= 0:
				continue

			slots.append(
				{
					"date": free_start_local.date(),
					"day": free_start_local.strftime("%A"),
					"duration": duration_seconds,
					"from_time": free_start_local.strftime("%H:%M:%S"),
					"to_time": free_end_local.strftime("%H:%M:%S"),
				}
			)

		current_date += timedelta(days=1)

	unique = {}
	for row in slots:
		key = (row["date"], row["from_time"], row["to_time"])
		if key not in unique:
			unique[key] = row

	return sorted(unique.values(), key=lambda d: (d["date"], d["from_time"], d["to_time"]))


@frappe.whitelist()
def get_busy_slots(employee: str, from_date: str, to_date: str, tz_name: str | None = None):
	"""Return all busy slots from Mailcow in the given date range."""
	if not employee:
		frappe.throw(_("Employee is required."))
	if not from_date or not to_date:
		frappe.throw(_("From Date and To Date are required."))

	start_date = getdate(from_date)
	end_date = getdate(to_date)
	if start_date > end_date:
		frappe.throw(_("From Date cannot be after To Date."))

	user_id, _ = _resolve_employee_calendar_user(employee)
	return _build_busy_slots_for_range(user_id, start_date, end_date, tz_name=tz_name)


@frappe.whitelist()
def get_free_slots(
	employee: str,
	from_date: str,
	to_date: str,
	tz_name: str | None = None,
	time_from: str = DEFAULT_TIME_FROM,
	time_to: str = DEFAULT_TIME_TO,
):
	"""Return available slots from the employee's calendar."""

	if not employee:
		frappe.throw(_("Employee is required."))

	if not from_date or not to_date:
		frappe.throw(_("From Date and To Date are required."))

	start_date = getdate(from_date)
	end_date = getdate(to_date)

	if start_date > end_date:
		frappe.throw(_("From Date cannot be after To Date."))

	user_id, _ = _resolve_employee_calendar_user(employee)

	# Use the same timezone resolution as the Calendar.
	# Passing None makes _resolve_calendar_timezone() use
	# the timezone configured in the User record.
	available_slots = _build_free_slots_for_range(
		user_id=user_id,
		from_date=start_date,
		to_date=end_date,
		tz_name=None,
		time_from=time_from,
		time_to=time_to,
	)

	# Apply the same Optional-slot exclusion used by the Calendar.
	available_slots = _exclude_optional_from_slot_rows(available_slots)
	# Remove Saturdays and Sundays.
	available_slots = [
		slot
		for slot in available_slots
		if slot["date"].weekday() < 5
	]

	return available_slots


def _ensure_dict_filters(filters):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)

	if isinstance(filters, dict):
		return filters

	if isinstance(filters, list):
		normalized = {}
		for item in filters:
			if isinstance(item, dict):
				fieldname = item.get("fieldname") or item.get("field") or item.get("name")
				if fieldname:
					normalized[fieldname] = item.get("value")
				continue

			if isinstance(item, (list, tuple)):
				# Common Frappe shape: [doctype, fieldname, operator, value]
				if len(item) >= 4:
					fieldname = item[1]
					if fieldname:
						normalized[fieldname] = item[3]
					continue

				# Legacy shape: [fieldname, operator, value]
				if len(item) >= 3:
					fieldname = item[0]
					if fieldname:
						normalized[fieldname] = item[2]

		return normalized

	return {}


def _resolve_employee_from_filters(filters: dict):
	employee = (filters.get("employee") or "").strip() if isinstance(filters.get("employee"), str) else filters.get("employee")
	if employee:
		return employee

	# Fallback: use employee linked to current session user.
	return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


def _iter_dates(from_date, to_date):
	current_date = from_date
	while current_date <= to_date:
		yield current_date
		current_date += timedelta(days=1)


def _to_event(date_value, start_time: str, end_time: str, title: str, slot_status: str):
	return {
		"name": f"{slot_status}-{date_value}-{start_time}-{end_time}",
		"title": title,
		"start": f"{date_value} {start_time}",
		"end": f"{date_value} {end_time}",
		"allDay": 0,
		"slot_status": slot_status,
		"color": STATUS_COLORS.get(slot_status),
	}


def _date_range_from_calendar(start: str, end: str):
	start_date = getdate(start)
	end_date = getdate(end)
	# Frappe calendar passes end as exclusive.
	if end_date > start_date:
		end_date = end_date - timedelta(days=1)
	return start_date, end_date


def _get_booked_events(user_id: str, from_date, to_date):
	booked_events, tz = _fetch_mailcow_events_for_range(
		user_id=user_id,
		from_date=from_date,
		to_date=to_date,
		time_from="00:00",
		time_to="23:59",
		tz_name=None,
		include_all_calendars=INCLUDE_ALL_CALENDARS,
	)

	events = []
	for event in booked_events:
		local_start = event["start_utc"].astimezone(tz)
		local_end = event["end_utc"].astimezone(tz)
		event_title = (event.get("title") or "").strip() or "Booked"
		events.append(
			{
				"name": f"Booked-{event.get('uid') or ''}-{local_start.isoformat()}-{local_end.isoformat()}",
				"title": event_title,
				"start": local_start.strftime("%Y-%m-%d %H:%M:%S"),
				"end": local_end.strftime("%Y-%m-%d %H:%M:%S"),
				"allDay": 0,
				"slot_status": "Booked",
				"color": STATUS_COLORS["Booked"],
				"description": event.get("description") or "",
				"location": event.get("location") or "",
			}
		)

	return events


def _get_optional_events(from_date, to_date):
	events = []
	for date_value in _iter_dates(from_date, to_date):
		for _, start_time, end_time in OPTIONAL_SLOTS:
			events.append(_to_event(date_value, f"{start_time}:00", f"{end_time}:00", "", "Optional"))
	return events


def _exclude_optional_from_slot_rows(slot_rows):
	"""Calendar-only: remove optional windows from available slot rows."""
	adjusted = []
	for slot in slot_rows or []:
		date_value = slot.get("date")
		if hasattr(date_value, "strftime"):
			date_text = date_value.strftime("%Y-%m-%d")
		else:
			date_text = str(date_value)

		start_dt = datetime.strptime(f"{date_text} {slot['from_time']}", "%Y-%m-%d %H:%M:%S")
		end_dt = datetime.strptime(f"{date_text} {slot['to_time']}", "%Y-%m-%d %H:%M:%S")
		if end_dt <= start_dt:
			continue

		optional_intervals = []
		for _, optional_from, optional_to in OPTIONAL_SLOTS:
			opt_start = datetime.strptime(f"{date_text} {optional_from}:00", "%Y-%m-%d %H:%M:%S")
			opt_end = datetime.strptime(f"{date_text} {optional_to}:00", "%Y-%m-%d %H:%M:%S")
			if opt_end > start_dt and opt_start < end_dt:
				optional_intervals.append((opt_start, opt_end))

		remaining = _subtract_intervals([(start_dt, end_dt)], optional_intervals)
		for rem_start, rem_end in remaining:
			duration_seconds = int((rem_end - rem_start).total_seconds())
			if duration_seconds <= 0:
				continue

			adjusted.append(
				{
					"date": rem_start.date(),
					"day": rem_start.strftime("%A"),
					"duration": duration_seconds,
					"from_time": rem_start.strftime("%H:%M:%S"),
					"to_time": rem_end.strftime("%H:%M:%S"),
				}
			)

	unique = {}
	for row in adjusted:
		key = (row["date"], row["from_time"], row["to_time"])
		if key not in unique:
			unique[key] = row

	return sorted(unique.values(), key=lambda d: (d["date"], d["from_time"], d["to_time"]))


@frappe.whitelist()
def get_employee_availability_calendar_events(start, end, filters=None):
	"""Calendar data source for Employee Availability view."""
	filters = _ensure_dict_filters(filters)
	employee = _resolve_employee_from_filters(filters)
	if not employee:
		frappe.throw(
			_(
				"Please select an Employee in the calendar filters, or link an Employee record to your User account."
			)
		)

	from_date, to_date = _date_range_from_calendar(start, end)
	if from_date > to_date:
		return []

	date_filter = filters.get("date")
	if date_filter:
		selected_date = getdate(date_filter)
		from_date = selected_date
		to_date = selected_date

	status_filter = (filters.get("slot_status") or "All").strip()
	user_id, _employee_email = _resolve_employee_calendar_user(employee)
	events = []

	if status_filter in ("All", "Available"):
		available_slots = _build_free_slots_for_range(user_id, from_date, to_date)
		available_slots = _exclude_optional_from_slot_rows(available_slots)
		for slot in available_slots:
			events.append(
				_to_event(
					slot["date"],
					slot["from_time"],
					slot["to_time"],
					"",
					"Available",
				)
			)

	if status_filter in ("All", "Booked"):
		events.extend(_get_booked_events(user_id, from_date, to_date))

	if status_filter in ("All", "Optional"):
		events.extend(_get_optional_events(from_date, to_date))

	return events