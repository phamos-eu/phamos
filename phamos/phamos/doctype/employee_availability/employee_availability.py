# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import add_to_date, getdate, nowdate

from phamos.mailcow_integration.availability.caldav_read import fetch_busy_intervals_from_sogo
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


def _parse_hhmm_to_hour_minute(value: str):
	hour, minute = (value or "").split(":")
	return int(hour), int(minute)


def _subtract_busy_from_window(busy_intervals, window_start_utc, window_end_utc):
	free = []
	current = window_start_utc

	for start, end in busy_intervals:
		# Ignore intervals fully outside the target window.
		if end <= window_start_utc or start >= window_end_utc:
			continue

		start = max(start, window_start_utc)
		end = min(end, window_end_utc)
		if end <= current:
			continue
		if start > current:
			free.append((current, start))
		current = max(current, end)
		if current >= window_end_utc:
			break

	if current < window_end_utc:
		free.append((current, window_end_utc))

	return [slot for slot in free if slot[1] > slot[0]]


def _build_available_slots_for_range(user_id: str, from_date, to_date):
	import pytz

	tz_name = frappe.db.get_value("User", user_id, "time_zone") or get_site_timezone()
	tz = pytz.timezone(tz_name)

	start_hour, start_minute = _parse_hhmm_to_hour_minute(DEFAULT_TIME_FROM)
	end_hour, end_minute = _parse_hhmm_to_hour_minute(DEFAULT_TIME_TO)

	# Fetch busy intervals once for the whole date span, then split into per-day windows locally.
	full_start_local = tz.localize(datetime(from_date.year, from_date.month, from_date.day, start_hour, start_minute, 0))
	full_end_local = tz.localize(datetime(to_date.year, to_date.month, to_date.day, end_hour, end_minute, 0))
	full_start_utc = full_start_local.astimezone(timezone.utc)
	full_end_utc = full_end_local.astimezone(timezone.utc)

	busy_intervals_all = fetch_busy_intervals_from_sogo(user_id, full_start_utc, full_end_utc)

	slots = []
	current_date = from_date
	while current_date <= to_date:
		window_start_local = tz.localize(datetime(current_date.year, current_date.month, current_date.day, start_hour, start_minute, 0))
		window_end_local = tz.localize(datetime(current_date.year, current_date.month, current_date.day, end_hour, end_minute, 0))

		if window_end_local <= window_start_local:
			current_date += timedelta(days=1)
			continue

		window_start_utc = window_start_local.astimezone(timezone.utc)
		window_end_utc = window_end_local.astimezone(timezone.utc)
		free_intervals = _subtract_busy_from_window(busy_intervals_all, window_start_utc, window_end_utc)

		for free_start_utc, free_end_utc in free_intervals:
			free_start_local = free_start_utc.astimezone(tz)
			free_end_local = free_end_utc.astimezone(tz)
			duration_seconds = int((free_end_utc - free_start_utc).total_seconds())

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
def generate_available_slots(employee: str, from_date: str, to_date: str):
	"""Fetch free intervals from Mailcow API for the employee calendar in the given date range."""
	if not employee:
		frappe.throw(_("Employee is required."))
	if not from_date or not to_date:
		frappe.throw(_("From Date and To Date are required."))

	start_date = getdate(from_date)
	end_date = getdate(to_date)
	if start_date > end_date:
		frappe.throw(_("From Date cannot be after To Date."))

	user_id, _user_email = _resolve_employee_calendar_user(employee)
	return _build_available_slots_for_range(user_id, start_date, end_date)