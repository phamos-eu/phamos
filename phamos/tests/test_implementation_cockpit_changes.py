# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

"""Plan changes in the Implementation Cockpit: the Decisions list, the proposal preview and the
open proposals on the Roadmap (#2219, child #2241)."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from phamos.api.implementation_cockpit import get_changes, get_overview, get_roadmap, preview_chapter_dates
from phamos.phamos.doctype.implementation_change.implementation_change import (
	AWAITING,
	_insert_change,
	agree_change,
)
from phamos.phamos.doctype.implementation_change.test_implementation_change import (
	CUSTOMER_USER,
	OUTSIDER_USER,
	_website_user,
	propose_change,
)
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import make_implementation
from phamos.tests.test_implementation_cockpit_roadmap import bars, make_chapter


class TestCockpitChanges(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.contact = _website_user(CUSTOMER_USER)
		_website_user(OUTSIDER_USER)

	def setUp(self):
		frappe.set_user("Administrator")
		implementation = frappe.get_doc("Implementation", make_implementation().name)
		implementation.show_on_customer_portal = 1
		implementation.append(
			"stakeholders", {"contact": self.contact, "full_name": "IC Customer", "stakeholder_organisation": "Customer"}
		)
		implementation.save()
		self.implementation = implementation.name
		# make_chapter (roadmap tests): planned, L2 → L4
		self.first = make_chapter(self.implementation, "First", "2026-01-01", "2026-01-10")
		self.second = make_chapter(self.implementation, "Second", "2026-01-11", "2026-01-20", depends_on=[self.first])

	def tearDown(self):
		frappe.set_user("Administrator")

	def propose(self, chapter, values, change_type="Dates"):
		return propose_change(self.implementation, "Implementation Chapter", change_type, values, chapter, reason="Why")

	def test_both_sides_see_what_waits_for_them_and_what_they_may_do(self):
		staff = self.propose(self.first, {"target_date": "2026-01-12"})
		frappe.set_user(CUSTOMER_USER)
		customer = self.propose(self.second, {"target_level": 5}, "Target level")
		frappe.set_user("Administrator")
		direct = _insert_change(
			self.implementation,
			"Implementation Chapter",
			self.second,
			"Dates",
			{"target_date": "2026-01-20"},
			{"target_date": "2026-01-25"},
			status=AWAITING,
			agreed_by_phamos="Administrator",
		).name

		def by_name(data):
			return {row["name"]: row for row in data["changes"]}

		phamos = get_changes(self.implementation)
		rows = by_name(phamos)
		self.assertEqual(phamos["side"], "phamos")
		self.assertEqual(
			{name: (rows[name]["waiting_for"], rows[name]["actions"]) for name in (staff, customer, direct)},
			{staff: ("customer", ["withdraw"]), customer: ("phamos", ["agree", "reject"]), direct: ("customer", [])},
		)
		self.assertEqual(phamos["waiting_count"], 1)
		row = rows[staff]
		self.assertEqual((row["target"]["label"], row["reason"], row["proposed_by"]["side"]), ("First", "Why", "phamos"))
		self.assertEqual(
			[(v["field"], v["label"], str(v["old"]), str(v["new"])) for v in row["values"]],
			[("target_date", "Target Date", "2026-01-10", "2026-01-12")],
		)
		self.assertEqual(get_overview(self.implementation)["decisions_waiting"], 1)

		frappe.set_user(CUSTOMER_USER)
		customer_view = get_changes(self.implementation)
		rows = by_name(customer_view)
		self.assertEqual(
			{name: rows[name]["actions"] for name in (staff, customer, direct)},
			{staff: ["agree", "reject"], customer: ["withdraw"], direct: ["confirm", "dispute"]},
		)
		self.assertEqual(customer_view["waiting_count"], 2)
		self.assertEqual(get_overview(self.implementation)["decisions_waiting"], 2)
		# no e-mail addresses leave the server, only names
		self.assertNotIn("@", frappe.as_json(customer_view))

		frappe.set_user(OUTSIDER_USER)
		self.assertRaises(frappe.PermissionError, get_changes, self.implementation)

	def test_a_decided_change_waits_for_nobody(self):
		name = self.propose(self.first, {"target_date": "2026-01-12"})
		frappe.set_user(CUSTOMER_USER)
		agree_change(name)
		row = next(r for r in get_changes(self.implementation)["changes"] if r["name"] == name)
		self.assertEqual((row["status"], row["waiting_for"], row["actions"]), ("Applied", None, []))
		self.assertEqual(row["agreed_by_customer"], frappe.db.get_value("Contact", self.contact, "full_name"))

	def test_the_preview_shows_the_new_end_date_and_clashes(self):
		# First ends on the 10th, Second starts on the 11th and ends on the 20th
		later = preview_chapter_dates(self.implementation, self.first, target_date="2026-01-15")
		self.assertEqual(later["clashes"], [{"chapter": self.second, "title": "Second", "direction": "needed by"}])
		self.assertEqual(later["end_shift_days"], 0)
		longer = preview_chapter_dates(self.implementation, self.second, target_date="2026-01-25")
		self.assertEqual((longer["end_shift_days"], longer["clashes"]), (5, []))
		self.assertEqual(longer["end_date"]["new"], getdate("2026-01-25"))
		earlier = preview_chapter_dates(self.implementation, self.second, planned_start="2026-01-05")
		self.assertEqual([c["direction"] for c in earlier["clashes"]], ["depends on"])
		# nothing was saved
		self.assertEqual(str(frappe.db.get_value("Implementation Chapter", self.first, "target_date")), "2026-01-10")
		self.assertRaises(frappe.ValidationError, preview_chapter_dates, self.implementation, self.first, target_date="2025-12-01")
		draft = make_chapter(self.implementation, "Idea", "2026-02-01", "2026-02-10", plan=False)
		self.assertRaises(frappe.ValidationError, preview_chapter_dates, self.implementation, draft, target_date="2026-02-20")

	def test_the_roadmap_carries_open_proposals_on_their_chapter(self):
		dates = self.propose(self.first, {"target_date": "2026-01-12"})
		level = self.propose(self.first, {"target_level": 5}, "Target level")
		frappe.set_user(CUSTOMER_USER)
		data = get_roadmap(self.implementation)
		self.assertTrue(data["can_propose"])
		chapter = bars(data)[self.first]
		self.assertEqual(
			{(p["name"], p["change_type"], tuple(p["actions"])) for p in chapter["proposals"]},
			{(dates, "Dates", ("agree", "reject")), (level, "Target level", ("agree", "reject"))},
		)
		self.assertEqual(bars(data)[self.second]["proposals"], [])
		agree_change(dates)
		self.assertEqual([p["name"] for p in bars(get_roadmap(self.implementation))[self.first]["proposals"]], [level])
