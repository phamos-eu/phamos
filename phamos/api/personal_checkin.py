# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Employee check-in and check-out from the Personal Cockpit (phamos/phamos#1571).

The logs are plain HRMS Employee Checkins of the session user's own Employee, so shifts,
auto attendance and HR reports keep working. On top of HRMS this module:

- stamps the time on the server (`time` is permlevel 1 in HRMS; a client time is never used);
- makes IN and OUT alternate (HRMS accepts two INs in a row), which also stops double clicks
  and a second tab from logging twice;
- allows the user to revoke a log they just made, for a short window.

Everything degrades to "not available" when HRMS is not installed or the user has no
active Employee.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, getdate, now_datetime, time_diff_in_seconds, today

from phamos.cockpits.defaults import CHECKIN_DEVICE_ID, CHECKIN_REVOKE_SECONDS, CHECKIN_UNDO_SECONDS
from phamos.cockpits.workdays import _employee

DOCTYPE = "Employee Checkin"
LOG_TYPES = ("IN", "OUT")
LOG_FIELDS = ["name", "log_type", "time", "device_id", "owner", "attendance"]
DASHBOARD_PERIODS = (7, 30, 90)
LIST_PAGE = 100


def available():
	return bool(frappe.db.exists("DocType", DOCTYPE))


def _geolocation_required():
	if not frappe.db.exists("DocType", "HR Settings"):
		return False
	return bool(cint(frappe.db.get_single_value("HR Settings", "allow_geolocation_tracking")))


def next_action(last):
	"""The opposite of the last log overall (as the HRMS app does); IN when there is none."""
	return "OUT" if last and last.get("log_type") == "IN" else "IN"


def worked_minutes(logs, now=None):
	"""Minutes between IN and OUT pairs, in time order; an open IN counts until `now` (and not
	at all without `now`, e.g. a past day whose check-out is missing).

	An OUT without an IN before it (e.g. the IN was yesterday) is ignored.
	"""
	total = 0
	open_in = None
	for log in sorted(logs, key=lambda log: get_datetime(log["time"])):
		if log.get("log_type") == "IN":
			if open_in is None:
				open_in = get_datetime(log["time"])
		elif log.get("log_type") == "OUT" and open_in is not None:
			total += max(time_diff_in_seconds(log["time"], open_in), 0)
			open_in = None
	if open_in is not None and now is not None:
		total += max(time_diff_in_seconds(now, open_in), 0)
	return int(total // 60)


def _brief(row):
	return {"name": row.name, "log_type": row.log_type, "time": row.time}


def get_checkin_state():
	state = {
		"available": available(),
		"employee": None,
		"employee_name": None,
		"can_checkin": False,
		"can_revoke": False,
		"geolocation_required": False,
		"last": None,
		"next_action": "IN",
		"stale_in": False,
		"today": {"logs": [], "worked_minutes": 0, "open_since": None},
		"undo_seconds": CHECKIN_UNDO_SECONDS,
		"server_now": now_datetime(),
	}
	if not state["available"]:
		return state
	employee = _employee(frappe.session.user)
	if not employee:
		return state

	now = state["server_now"]
	last = frappe.get_all(
		DOCTYPE, filters={"employee": employee}, fields=LOG_FIELDS, order_by="time desc, creation desc", limit=1
	)
	last = last[0] if last else None
	logs = frappe.get_all(
		DOCTYPE,
		filters={"employee": employee, "time": (">=", get_datetime(today()))},
		fields=LOG_FIELDS,
		order_by="time asc, creation asc",
	)
	action = next_action(last)
	state.update(
		{
			"employee": employee,
			"employee_name": frappe.db.get_value("Employee", employee, "employee_name"),
			"can_checkin": bool(frappe.has_permission(DOCTYPE, "create")),
			"can_revoke": bool(frappe.has_permission(DOCTYPE, "delete")),
			"geolocation_required": _geolocation_required(),
			"last": _brief(last) if last else None,
			"next_action": action,
			"stale_in": bool(last and last.log_type == "IN" and getdate(last.time) < getdate(today())),
			"today": {
				"logs": [_brief(row) for row in logs],
				"worked_minutes": worked_minutes(logs, now),
				"open_since": last.time if action == "OUT" else None,
			},
		}
	)
	return state


def _require_employee():
	if not available():
		frappe.throw(_("Check-ins need the HR app, which is not installed on this site."))
	employee = _employee(frappe.session.user)
	if not employee:
		frappe.throw(_("Your user is not linked to an active Employee."))
	return employee


def add_checkin(log_type, latitude=None, longitude=None):
	"""Log IN or OUT for my Employee now. Refused unless it is the expected next action."""
	if log_type not in LOG_TYPES:
		frappe.throw(_("Log type must be IN or OUT."))
	employee = _require_employee()

	state = get_checkin_state()
	if log_type != state["next_action"]:
		last = state["last"]
		when = frappe.format(last["time"], "Datetime") if last else ""
		message = _("Already checked in at {0}.") if log_type == "IN" else _("Already checked out at {0}.")
		frappe.throw(message.format(when) if last else _("You are not checked in."))

	latitude, longitude = (float(latitude), float(longitude)) if latitude and longitude else (None, None)
	if state["geolocation_required"] and latitude is None:
		frappe.throw(_("Your location is required for checking in. Please allow location access."))

	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"employee": employee,
			"log_type": log_type,
			"time": now_datetime(),
			"device_id": CHECKIN_DEVICE_ID,
			"skip_auto_attendance": 0,
			"latitude": latitude,
			"longitude": longitude,
		}
	)
	doc.insert()
	return {"log": {"name": doc.name, "log_type": doc.log_type, "time": doc.time}, "state": get_checkin_state()}


def revoke_checkin(name):
	"""Delete a log I made moments ago (the undo of the cockpit's one-click check-in)."""
	employee = _require_employee()
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.employee != employee or doc.owner != frappe.session.user:
		frappe.throw(_("Only your own check-ins can be revoked."), frappe.PermissionError)
	if doc.get("attendance"):
		frappe.throw(_("This check-in already counts for attendance and can no longer be revoked."))
	if time_diff_in_seconds(now_datetime(), doc.creation) > CHECKIN_REVOKE_SECONDS:
		frappe.throw(_("This check-in can no longer be revoked. Please ask HR to correct it."))
	frappe.delete_doc(DOCTYPE, name)
	return get_checkin_state()


def _minute_of_day(value):
	value = get_datetime(value)
	return value.hour * 60 + value.minute


def day_summaries(logs, now, today_date):
	"""Per day: first IN, last OUT, worked minutes, and whether the check-out is missing."""
	by_day = {}
	for log in sorted(logs, key=lambda log: get_datetime(log["time"])):
		by_day.setdefault(getdate(log["time"]), []).append(log)
	days = []
	for day, day_logs in sorted(by_day.items()):
		ins = [log for log in day_logs if log["log_type"] == "IN"]
		outs = [log for log in day_logs if log["log_type"] == "OUT"]
		is_today = day == today_date
		days.append(
			{
				"date": day,
				"first_in": ins[0]["time"] if ins else None,
				"last_out": outs[-1]["time"] if outs else None,
				"worked_minutes": worked_minutes(day_logs, now if is_today else None),
				"logs": len(day_logs),
				"missing_out": day_logs[-1]["log_type"] == "IN" and not is_today,
			}
		)
	return days


def _average(values):
	values = [v for v in values if v is not None]
	return round(sum(values) / len(values)) if values else None


def get_checkin_dashboard(period=30):
	"""My check-in figures for the last `period` days (7, 30 or 90), today included."""
	period = cint(period) or 30
	if period not in DASHBOARD_PERIODS:
		frappe.throw(_("Period must be one of {0} days.").format(", ".join(map(str, DASHBOARD_PERIODS))))
	state = get_checkin_state()
	result = {"period": period, "state": state, "days": [], "totals": None}
	if not state["employee"]:
		return result

	now = state["server_now"]
	today_date = getdate(today())
	start = add_days(today_date, -(period - 1))
	logs = frappe.get_all(
		DOCTYPE,
		filters={"employee": state["employee"], "time": (">=", get_datetime(start))},
		fields=["name", "log_type", "time"],
		order_by="time asc",
	)
	days = day_summaries(logs, now, today_date)
	worked = [d for d in days if d["worked_minutes"]]
	week_start = today_date - timedelta(days=today_date.weekday())
	result["days"] = days
	result["totals"] = {
		"worked_minutes": sum(d["worked_minutes"] for d in days),
		"days_worked": len(worked),
		"average_minutes": _average([d["worked_minutes"] for d in worked]),
		"average_start": _average([_minute_of_day(d["first_in"]) for d in days if d["first_in"]]),
		"average_end": _average([_minute_of_day(d["last_out"]) for d in days if d["last_out"] and not d["missing_out"]]),
		"week_minutes": sum(d["worked_minutes"] for d in days if d["date"] >= week_start),
		"missing_out": [d for d in days if d["missing_out"]],
	}
	return result


def get_my_checkins(start=0, page_length=LIST_PAGE):
	"""All my check-ins, newest first, a page at a time."""
	state_employee = _employee(frappe.session.user) if available() else None
	if not state_employee:
		return {"employee": None, "logs": [], "has_more": False}
	start, page_length = max(cint(start), 0), min(max(cint(page_length), 1), 500)
	rows = frappe.get_all(
		DOCTYPE,
		filters={"employee": state_employee},
		fields=["name", "log_type", "time", "device_id", "shift", "attendance", "skip_auto_attendance"],
		order_by="time desc, creation desc",
		start=start,
		page_length=page_length + 1,
	)
	return {"employee": state_employee, "logs": rows[:page_length], "has_more": len(rows) > page_length}
