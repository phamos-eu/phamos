# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

"""Roadmap data of the Implementation Cockpit (#2033, part of #1694)."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from phamos.api.implementation_cockpit import get_roadmap
from phamos.phamos.doctype.implementation_baseline.implementation_baseline import create_baseline
from phamos.phamos.doctype.implementation_chapter.implementation_chapter import set_as_planned
from phamos.phamos.doctype.implementation_change.test_implementation_change import (
	CUSTOMER_USER,
	OUTSIDER_USER,
	_website_user,
)
from phamos.phamos.doctype.implementation_feature.test_implementation_feature import make_feature
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import make_implementation
from phamos.tests.test_implementation_cockpit_features import module


def make_chapter(implementation, title, start, target, module=None, depends_on=(), plan=True):
	chapter = frappe.get_doc(
		{
			"doctype": "Implementation Chapter",
			"implementation": implementation,
			"status": "Draft",
			"chapter_title": title,
			"full_chapter_description": f"{title} description",
			"planned_start": start,
			"target_date": target,
			"current_level": 2,
			"target_level": 4,
			"module": module,
			"depends_on": [{"chapter": name} for name in depends_on],
		}
	).insert(ignore_permissions=True)
	if plan:
		set_as_planned(chapter.name)
	return chapter.name


def bars(data):
	return {bar["name"]: bar for row in [*data["modules"], data["no_module"]] for bar in row["bars"]}


def row_of(data, module_name):
	return next(row for row in data["modules"] if row["module"] == module_name)


class TestCockpitRoadmap(FrappeTestCase):
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
		self.warehouse = module("_Test RM Warehouse")
		self.sales = module("_Test RM Sales")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_only_people_with_access_get_the_roadmap(self):
		make_chapter(make_implementation().name, "Elsewhere", "2026-01-01", "2026-01-10", self.warehouse)
		frappe.set_user(OUTSIDER_USER)
		self.assertRaises(frappe.PermissionError, get_roadmap, self.implementation)
		frappe.set_user(CUSTOMER_USER)
		self.assertEqual(bars(get_roadmap(self.implementation)), {})

	def test_customers_get_no_draft_or_cancelled_chapters_and_cannot_propose(self):
		agreed = make_chapter(self.implementation, "Agreed", "2026-01-01", "2026-01-10", self.warehouse)
		draft = make_chapter(self.implementation, "Draft", "2026-01-11", "2026-01-20", self.warehouse, [agreed], plan=False)
		cancelled = make_chapter(self.implementation, "Gone", "2026-02-01", "2026-02-10", self.warehouse, plan=False)
		frappe.db.set_value("Implementation Chapter", cancelled, "status", "Cancelled")

		staff = get_roadmap(self.implementation)
		self.assertEqual(set(bars(staff)), {agreed, draft, cancelled})
		self.assertEqual(staff["dependencies"], [{"from": agreed, "to": draft, "conflict": False}])
		self.assertTrue(staff["can_propose"])

		frappe.get_doc(
			{
				"doctype": "Implementation Release",
				"title": "R draft",
				"implementation": self.implementation,
				"chapter": draft,
				"target_date": "2026-01-25",
			}
		).insert(ignore_permissions=True)
		self.assertIn("R draft", [m["title"] for m in get_roadmap(self.implementation)["markers"]])

		frappe.set_user(CUSTOMER_USER)
		customer = get_roadmap(self.implementation)
		self.assertEqual(set(bars(customer)), {agreed})
		self.assertEqual(customer["dependencies"], [])
		self.assertFalse(customer["can_propose"])
		# a release planned against a Draft chapter stays hidden with it
		self.assertEqual(customer["markers"], [])

	def test_critical_path_and_slack_run_through_agreed_chapters_only(self):
		first = make_chapter(self.implementation, "First", "2026-01-01", "2026-01-10", self.warehouse)
		second = make_chapter(self.implementation, "Second", "2026-01-11", "2026-01-20", self.warehouse, [first])
		side = make_chapter(self.implementation, "Side", "2026-01-01", "2026-01-05", self.sales)
		draft = make_chapter(self.implementation, "Later", "2026-01-21", "2026-03-31", self.sales, [second], plan=False)
		data = bars(get_roadmap(self.implementation))
		self.assertEqual((data[first]["critical"], data[first]["slack_days"]), (True, 0))
		self.assertEqual((data[second]["critical"], data[second]["slack_days"]), (True, 0))
		self.assertEqual((data[side]["critical"], data[side]["slack_days"]), (False, 15))
		# a Draft chapter is drawn for staff, but doesn't move the end date
		self.assertIsNone(data[draft]["critical"])
		self.assertEqual((data[first]["current_level"], data[first]["target_level"]), (2, 4))

	def test_feature_events_and_release_markers(self):
		live = make_feature(self.implementation, title="Done", module=self.warehouse, status="In Testing", planned_start="2026-01-05")
		for status in ("Live", "In Testing", "Live"):
			live.reload()
			live.status = status
			live.save()
		live_rows = frappe.get_all(
			"Implementation Feature Progress", filters={"parent": live.name, "status": "Live"}, pluck="name", order_by="idx asc"
		)
		for name, day in zip(live_rows, ("2026-03-05", "2026-02-01")):
			frappe.db.set_value("Implementation Feature Progress", name, "date", day)
		loose = make_feature(self.implementation, title="Loose", planned_start="2026-01-08", target_date="2026-04-30")
		make_feature(self.implementation, title="Dropped", module=self.warehouse, status="Dropped", planned_start="2026-01-09")
		frappe.get_doc(
			{
				"doctype": "Implementation Release",
				"title": "R1",
				"implementation": self.implementation,
				"status": "Planned",
				"target_date": "2026-04-01",
				"features": [{"feature": loose.name}],
			}
		).insert(ignore_permissions=True)

		data = get_roadmap(self.implementation)
		events = {(e["title"], e["kind"]): getdate(e["date"]) for e in row_of(data, self.warehouse)["events"]}
		# the finished date is the latest Live row, not the first one; Dropped features don't show
		self.assertEqual(events, {("Done", "planned"): getdate("2026-01-05"), ("Done", "finished"): getdate("2026-03-05")})
		self.assertEqual([(e["title"], e["kind"]) for e in data["no_module"]["events"]], [("Loose", "planned")])
		release = next(m for m in data["markers"] if m["type"] == "release")
		self.assertEqual([f["name"] for f in release["late_features"]], [loose.name])
		self.assertEqual(data["range"]["end"], getdate("2026-04-01"))

	def test_a_module_row_without_a_chapter_is_a_bar_of_its_own(self):
		implementation = frappe.get_doc("Implementation", self.implementation)
		implementation.append(
			"modules",
			{"module": self.sales, "planned_start": "2026-05-01", "target_date": "2026-06-30", "current_level": 1, "target_level": 3},
		)
		implementation.save()
		row = row_of(get_roadmap(self.implementation), self.sales)
		self.assertEqual(len(row["bars"]), 1)
		bar = row["bars"][0]
		self.assertIsNone(bar["chapter"])
		self.assertEqual((getdate(bar["target_date"]), bar["target_level"], bar["critical"]), (getdate("2026-06-30"), 3, None))

	def test_baseline_shift_and_items_added_after_it(self):
		agreed = make_chapter(self.implementation, "Agreed", "2026-01-01", "2026-01-10", self.warehouse)
		create_baseline(self.implementation)
		# as an applied Implementation Change would: the agreed target moves five days
		frappe.db.set_value("Implementation Chapter", agreed, "target_date", "2026-01-15")
		added = make_chapter(self.implementation, "Added", "2026-02-01", "2026-02-10", self.warehouse)
		feature = make_feature(self.implementation, title="New", module=self.warehouse, planned_start="2026-02-02")

		data = get_roadmap(self.implementation)
		chapter_bars = bars(data)
		self.assertEqual(chapter_bars[agreed]["baseline"]["shift_days"], 5)
		self.assertFalse(chapter_bars[agreed]["is_new"])
		self.assertTrue(chapter_bars[added]["is_new"])
		self.assertIsNone(chapter_bars[added]["baseline"])
		self.assertTrue(next(e for e in row_of(data, self.warehouse)["events"] if e["name"] == feature.name)["is_new"])
		self.assertIsNotNone(data["baseline"])
