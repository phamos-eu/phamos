# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Self-set ToDo challenges (#1557). "Today" is pinned to Wednesday 2026-10-14; users have no
Employee record, so only weekends are days off."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from phamos.api import personal_challenges as challenges
from phamos.api import personal_cockpit as pc

USER = "ch-a@example.com"
OTHER = "ch-b@example.com"
TODAY = "2026-10-14"


def _ensure_user(email, roles=("Employee",)):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	missing = set(roles) - set(frappe.get_roles(email))
	if missing:
		frappe.get_doc("User", email).add_roles(*missing)


class TestToDoChallenges(FrappeTestCase):
	def setUp(self):
		mute = patch("frappe.desk.form.assign_to.notify_assignment")
		mute.start()
		self.addCleanup(mute.stop)
		frappe.set_user("Administrator")
		_ensure_user(USER)
		_ensure_user(OTHER, ("Employee", "System Manager"))
		pinned = patch.object(challenges, "today", return_value=TODAY)
		pinned.start()
		self.addCleanup(pinned.stop)
		no_employee = patch("phamos.cockpits.workdays._employee", return_value=None)
		no_employee.start()
		self.addCleanup(no_employee.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _closed(self, day, count=1, user=USER, important=0, status="Closed", minutes_open=120):
		for index in range(count):
			todo = frappe.get_doc(
				{"doctype": "ToDo", "allocated_to": user, "description": f"Closed on {day} #{index}"}
			).insert(ignore_permissions=True)
			closed = frappe.utils.add_to_date(f"{day} 08:00:00", minutes=minutes_open)
			frappe.db.set_value(
				"ToDo",
				todo.name,
				{
					"status": status,
					"cockpit_closed_on": closed,
					"cockpit_closed_by": user,
					"cockpit_important": important,
					"creation": f"{day} 08:00:00",
				},
				update_modified=False,
			)

	def _challenge(self, start, target=2, days=10, kind="Closes per day", user=USER):
		frappe.set_user(user)
		with patch.object(challenges, "today", return_value=start):
			created = pc.create_challenge(kind, target, days, start)
		return created

	def _results(self, data):
		return [(str(d["date"]), d["result"]) for d in data["days"]]

	def test_jokers_repair_and_welcome_back(self):
		for day, count in {
			"2026-10-05": 2,
			"2026-10-06": 0,
			"2026-10-07": 1,
			"2026-10-08": 0,
			"2026-10-09": 4,
			"2026-10-12": 2,
			"2026-10-13": 1,
			"2026-10-14": 1,
		}.items():
			if count:
				self._closed(day, count)
		self._challenge("2026-10-05")
		data = pc.get_challenges()["active"][0]
		self.assertEqual(
			self._results(data)[:8],
			[
				("2026-10-05", "Met"),
				("2026-10-06", "Joker"),
				("2026-10-07", "Joker"),
				("2026-10-08", "Repaired"),
				("2026-10-09", "Met"),
				("2026-10-12", "Met"),
				("2026-10-13", "Missed"),
				("2026-10-14", "Today"),
			],
		)
		self.assertEqual(data["counted_days"], 6)
		self.assertEqual((data["jokers_allowed"], data["jokers_left"]), (2, 0))
		self.assertEqual((data["current_streak"], data["best_streak"]), (0, 6))
		self.assertEqual(data["today"]["closes"], 1)
		self.assertEqual(data["today"]["repair"]["needs"], {"closes": 3})
		self.assertTrue(data["welcome_back"])
		self.assertEqual(str(data["end_date"]), "2026-10-16")

	def test_evaluation_is_idempotent(self):
		self._closed("2026-10-12", 2)
		self._challenge("2026-10-12", days=5)
		pc.get_challenges()
		pc.get_challenges()
		doc = frappe.get_doc("ToDo Challenge", frappe.get_all("ToDo Challenge", {"user": USER}, pluck="name")[0])
		self.assertEqual([(str(r.date), r.result) for r in doc.days], [("2026-10-12", "Met"), ("2026-10-13", "Joker")])

	def test_quick_wins_drops_and_others_do_not_count(self):
		self._closed("2026-10-13", 1, minutes_open=5)  # created and closed within 15 minutes
		self._closed("2026-10-13", 1, status="Cancelled")
		self._closed("2026-10-13", 1, user=OTHER)
		self._closed("2026-10-13", 1)
		self.assertEqual(challenges.closes_by_day(USER, "2026-10-13", "2026-10-13"), {getdate("2026-10-13"): 1})

	def test_important_kind_counts_only_important(self):
		self._closed("2026-10-13", 2)
		self._closed("2026-10-13", 1, important=1)
		self.assertEqual(
			challenges.closes_by_day(USER, "2026-10-13", "2026-10-13", "Important per day"), {getdate("2026-10-13"): 1}
		)

	def test_completed_when_every_day_counts(self):
		for day in ("2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"):
			self._closed(day, 2)
		self._challenge("2026-10-05", days=5)
		result = pc.get_challenges()
		self.assertEqual(result["active"], [])
		self.assertEqual(result["recent"][0]["status"], "Completed")

	def test_ended_not_failed_when_a_day_stays_missed(self):
		self._closed("2026-10-05", 2)
		self._challenge("2026-10-05", days=5)  # one joker; two empty days
		finished = pc.get_challenges()["recent"][0]
		self.assertEqual(finished["status"], "Ended")
		self.assertNotIn("Failed", frappe.get_meta("ToDo Challenge").get_field("status").options)

	def test_last_day_met_completes_the_same_day(self):
		for day in ("2026-10-08", "2026-10-09", "2026-10-12", "2026-10-13", "2026-10-14"):
			self._closed(day, 2)
		self._challenge("2026-10-08", days=5)
		self.assertEqual(pc.get_challenges()["recent"][0]["status"], "Completed")

	def test_end_early(self):
		self._challenge("2026-10-14")
		name = pc.get_challenges()["active"][0]["name"]
		self.assertEqual(pc.end_challenge(name)["status"], "Ended")

	def test_create_validation(self):
		frappe.set_user(USER)
		with self.assertRaises(frappe.ValidationError):
			pc.create_challenge("Closes per day", 2, 10, "2026-10-01")  # past
		with self.assertRaises(frappe.ValidationError):
			pc.create_challenge("Closes per day", 0, 10, TODAY)
		with self.assertRaises(frappe.ValidationError):
			pc.create_challenge("Closes per day", 2, 7, TODAY)
		with self.assertRaises(frappe.ValidationError):
			pc.create_challenge("Close everything", 2, 10, TODAY)
		created = pc.create_challenge("Closes per day", 2, 10, TODAY)
		self.assertEqual(created["title"], "Close 2 a day for 10 working days")
		self.assertEqual(created["jokers_allowed"], 2)
		with self.assertRaises(frappe.ValidationError):
			pc.create_challenge("Closes per day", 3, 5, TODAY)  # one per kind
		pc.create_challenge("Important per day", 1, 5, TODAY)

	def test_suggestion_from_own_median(self):
		for day in ("2026-10-12", "2026-10-13", "2026-10-09", "2026-10-08", "2026-10-07", "2026-10-06"):
			self._closed(day, 3)
		frappe.set_user(USER)
		with patch.object(challenges, "BASELINE_WORKING_DAYS", 10):
			suggestion = pc.suggest_challenge()
		self.assertEqual(suggestion["baseline_per_day"], 3.0)  # 6 of 10 days with 3
		self.assertEqual(suggestion["suggested"], 4)
		self.assertEqual(str(suggestion["next_monday"]), "2026-10-19")

	def test_challenges_are_private(self):
		self._challenge(TODAY)
		frappe.set_user(USER)
		name = pc.get_challenges()["active"][0]["name"]
		frappe.set_user(OTHER)
		self.assertEqual(pc.get_challenges()["active"], [])
		self.assertNotIn(name, frappe.get_list("ToDo Challenge", pluck="name"))
		with self.assertRaises(frappe.PermissionError):
			pc.end_challenge(name)
