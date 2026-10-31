# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Personal Cockpit ToDo lifecycle and dashboard (#1553): closed-on stamps, reschedule count,
metrics and the Decide dialog, exercised by users who are not System Managers."""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, now_datetime, today

from phamos.api import dashboard_metrics as dm
from phamos.api import personal_cockpit as pc
from phamos.api import personal_todos
from phamos.cockpits.setup import ensure_todo_fields

USER_A = "dash-a@example.com"
USER_B = "dash-b@example.com"


def _ensure_user(email):
	"""A plain desk user: no System Manager, so ToDo permission rules apply."""
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	if "Employee" not in frappe.get_roles(email):
		frappe.get_doc("User", email).add_roles("Employee")
	return email


def _todo(user, description="Do something", **values):
	return frappe.get_doc(
		{"doctype": "ToDo", "allocated_to": user, "description": description, **values}
	).insert(ignore_permissions=True)


def _set_times(name, creation=None, closed_on=None):
	values = {}
	if creation:
		values["creation"] = creation
	if closed_on:
		values["cockpit_closed_on"] = closed_on
	frappe.db.set_value("ToDo", name, values, update_modified=False)


class DashboardTestCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_todo_fields()

	def setUp(self):
		# Assignment notifications send an e-mail at once in tests, and the queue commits.
		mute = patch("frappe.desk.form.assign_to.notify_assignment")
		mute.start()
		self.addCleanup(mute.stop)
		frappe.set_user("Administrator")
		_ensure_user(USER_A)
		_ensure_user(USER_B)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()


class TestLifecycleStamps(DashboardTestCase):
	def test_closing_stamps_and_reopening_clears(self):
		todo = _todo(USER_A)
		frappe.set_user(USER_A)
		pc.close_todo(todo.name)
		row = frappe.db.get_value("ToDo", todo.name, ["cockpit_closed_on", "cockpit_closed_by"], as_dict=True)
		self.assertIsNotNone(row.cockpit_closed_on)
		self.assertEqual(row.cockpit_closed_by, USER_A)

		pc.reopen_todo(todo.name)
		row = frappe.db.get_value("ToDo", todo.name, ["cockpit_closed_on", "cockpit_closed_by"], as_dict=True)
		self.assertIsNone(row.cockpit_closed_on)
		self.assertIsNone(row.cockpit_closed_by)

	def test_desk_assignment_close_and_removal_are_stamped(self):
		issue = frappe.get_doc({"doctype": "Issue", "subject": "Stamped"}).insert(ignore_permissions=True)
		from frappe.desk.form import assign_to

		assign_to.add({"doctype": "Issue", "name": issue.name, "assign_to": [USER_A], "description": "x"})
		frappe.set_user(USER_A)
		assign_to.close("Issue", issue.name, USER_A)
		closed = frappe.get_value("ToDo", {"reference_name": issue.name, "allocated_to": USER_A}, ["status", "cockpit_closed_by"], as_dict=True)
		self.assertEqual(closed.status, "Closed")
		self.assertEqual(closed.cockpit_closed_by, USER_A)

	def test_moving_the_date_later_counts_a_reschedule(self):
		todo = _todo(USER_A, date=today())
		self.assertEqual(str(frappe.db.get_value("ToDo", todo.name, "cockpit_first_due_date")), today())
		frappe.set_user(USER_A)
		pc.update_todo(todo.name, date=add_days(today(), 2))
		pc.update_todo(todo.name, date=add_days(today(), 1))  # earlier: not a postponement
		pc.update_todo(todo.name, date=add_days(today(), 5))
		row = frappe.db.get_value("ToDo", todo.name, ["cockpit_reschedule_count", "cockpit_first_due_date"], as_dict=True)
		self.assertEqual(row.cockpit_reschedule_count, 2)
		self.assertEqual(str(row.cockpit_first_due_date), today())

	def test_new_todo_without_date_stays_undated_and_high_is_important(self):
		todo = _todo(USER_A, priority="High")
		row = frappe.db.get_value("ToDo", todo.name, ["date", "cockpit_important"], as_dict=True)
		self.assertIsNone(row.date)
		self.assertEqual(row.cockpit_important, 1)


class TestDecide(DashboardTestCase):
	def test_later_this_week(self):
		self.assertEqual(str(personal_todos.later_this_week("2026-10-12")), "2026-10-16")  # Monday → Friday
		self.assertEqual(str(personal_todos.later_this_week("2026-10-15")), "2026-10-16")  # Thursday → Friday
		self.assertEqual(str(personal_todos.later_this_week("2026-10-16")), "2026-10-20")  # Friday → Tuesday
		self.assertEqual(str(personal_todos.later_this_week("2026-10-18")), "2026-10-20")  # Sunday → Tuesday

	def test_drop_needs_a_reason_and_cancels(self):
		todo = _todo(USER_A)
		frappe.set_user(USER_A)
		with self.assertRaises(frappe.ValidationError):
			pc.decide_todo(todo.name, "drop")
		row = pc.decide_todo(todo.name, "drop", reason="Out of date")
		self.assertEqual(row["status"], "Cancelled")
		self.assertTrue(
			frappe.db.exists("Comment", {"reference_doctype": "ToDo", "reference_name": todo.name, "content": ("like", "%Out of date%")})
		)

	def test_plan_and_today_move_the_date(self):
		todo = _todo(USER_A, date=add_days(today(), -20))
		frappe.set_user(USER_A)
		self.assertEqual(str(pc.decide_todo(todo.name, "today")["date"]), today())
		planned = pc.decide_todo(todo.name, "plan", date=add_days(today(), 3))
		self.assertEqual(str(planned["date"]), add_days(today(), 3))
		self.assertEqual(planned["reschedule_count"], 2)
		with self.assertRaises(frappe.ValidationError):
			pc.decide_todo(todo.name, "plan", date=add_days(today(), -1))

	def test_someone_elses_todo_is_refused(self):
		todo = _todo(USER_B)
		frappe.set_user(USER_A)
		with self.assertRaises(frappe.PermissionError):
			pc.decide_todo(todo.name, "today")


class TestDashboard(DashboardTestCase):
	def test_counts_only_my_closures_in_the_window(self):
		now = now_datetime()
		mine = _todo(USER_A, "Closed by me")
		frappe.set_user(USER_A)
		pc.close_todo(mine.name)
		_set_times(mine.name, creation=now - timedelta(days=4), closed_on=now - timedelta(days=1))
		dropped = _todo(USER_A, "Dropped by me")
		pc.decide_todo(dropped.name, "drop", reason="Not needed any more")
		frappe.set_user("Administrator")
		by_admin = _todo(USER_A, "Closed by someone else")
		frappe.get_doc("ToDo", by_admin.name).update({"status": "Closed"}).save(ignore_permissions=True)
		old_open = _todo(USER_A, "Old open")
		_set_times(old_open.name, creation=now - timedelta(days=40))
		_todo(USER_B, "Not mine")

		frappe.set_user(USER_A)
		data = pc.get_todo_dashboard(30)
		current = data["windows"]["current"]
		self.assertEqual(current["closed"], 1)
		self.assertEqual(current["dropped"], 1)
		self.assertEqual(current["open"], 1)
		self.assertEqual(data["closures"]["by_others"], 1)
		self.assertEqual(data["lead_time"]["sample"], 1)
		self.assertAlmostEqual(data["lead_time"]["p50_days"], 3.0, places=1)
		self.assertEqual(data["oldest"][0]["name"], old_open.name)
		self.assertEqual(data["oldest"][0]["age_days"], 40)
		self.assertEqual(sum(b["value"] for b in data["aging"]), 1)
		self.assertEqual(len(data["flow"]), 5)

	def test_done_today_and_quick_wins(self):
		frappe.set_user(USER_A)
		quick = pc.create_todo("<p>Reply to Anna</p>")
		pc.close_todo(quick["name"])
		data = pc.get_todo_dashboard(7)
		self.assertEqual([d["name"] for d in data["today"]["done"]], [quick["name"]])
		self.assertTrue(data["today"]["done"][0]["quick_win"])
		self.assertEqual(data["closures"]["quick_wins"], 1)
		self.assertEqual(len(data["flow"]), 7)

	def test_stale_by_age_or_postponements(self):
		overdue = _todo(USER_A, "Long overdue", date=add_days(today(), -20))
		postponed = _todo(USER_A, "Postponed a lot", date=today())
		frappe.db.set_value("ToDo", postponed.name, "cockpit_reschedule_count", 3, update_modified=False)
		fresh = _todo(USER_A, "Fresh", date=today())
		frappe.set_user(USER_A)
		names = {row["name"] for row in pc.get_todo_dashboard(30)["stale"]}
		self.assertEqual(names, {overdue.name, postponed.name})
		self.assertTrue(pc.get_todo(overdue.name)["stale"])
		self.assertFalse(pc.get_todo(fresh.name)["stale"])

	def test_invalid_period_is_rejected(self):
		frappe.set_user(USER_A)
		with self.assertRaises(frappe.ValidationError):
			pc.get_todo_dashboard(14)


class TestMetricHelpers(FrappeTestCase):
	def test_percentile_nearest_rank(self):
		self.assertEqual(dm.percentile([5, 1, 3, 2, 4], 50), 3)
		self.assertEqual(dm.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 85), 9)
		self.assertIsNone(dm.percentile([], 50))

	def test_open_at_and_buckets(self):
		now = now_datetime()
		rows = [
			{"creation": now - timedelta(days=10), "cockpit_closed_on": now - timedelta(days=2)},
			{"creation": now - timedelta(days=3), "cockpit_closed_on": None},
			{"creation": now - timedelta(days=100), "cockpit_closed_on": None},
		]
		self.assertEqual(dm.open_at(rows, now - timedelta(days=5)), 2)
		buckets = dm.age_buckets([r for r in rows if not r["cockpit_closed_on"]], now, (("new", 0, 7), ("old", 8, None)))
		self.assertEqual([b["value"] for b in buckets], [1, 1])

	def test_weekly_windows_end_today(self):
		now = now_datetime()
		windows = dm.period_windows(now, 30)
		self.assertEqual(len(windows), 5)
		self.assertEqual(getdate(windows[-1][2]), getdate(add_days(today(), 1)))
		self.assertEqual(windows[-1][1].weekday(), 0)
