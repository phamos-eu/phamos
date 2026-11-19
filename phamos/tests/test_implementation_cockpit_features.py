# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

"""Features page of the Implementation Cockpit: list, Kanban moves and the WBS roll-up (#1972)."""

import random

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.implementation_cockpit import (
	get_feature,
	get_features,
	get_wbs,
	roll_up,
	set_feature_status,
)
from phamos.phamos.doctype.implementation_baseline.implementation_baseline import create_baseline
from phamos.phamos.doctype.implementation_change.test_implementation_change import (
	CUSTOMER_USER,
	OUTSIDER_USER,
	_website_user,
)
from phamos.phamos.doctype.implementation_feature.test_implementation_feature import make_feature
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import make_implementation


def module(name):
	if not frappe.db.exists("Implementation Module", name):
		frappe.get_doc({"doctype": "Implementation Module", "module_name": name}).insert(ignore_permissions=True)
	return name


def gitlab_issue(feature, state="opened", estimate=0):
	frappe.get_doc(
		{
			"doctype": "GitLab Issue",
			"name": f"_Test FP {frappe.generate_hash(length=8)}",
			"issue_id": str(random.randint(10**8, 10**9)),
			"title": "work",
			"state": state,
			"implementation_feature": feature,
			"time_estimate_hours": estimate,
		}
	).db_insert()


class TestCockpitFeatures(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.contact = _website_user(CUSTOMER_USER)
		_website_user(OUTSIDER_USER)

	def setUp(self):
		frappe.set_user("Administrator")
		implementation = frappe.get_doc("Implementation", make_implementation().name)
		implementation.show_on_customer_portal = 1
		implementation.max_parallel_features = 1
		implementation.append(
			"stakeholders", {"contact": self.contact, "full_name": "IC Customer", "stakeholder_organisation": "Customer"}
		)
		implementation.save()
		self.implementation = implementation.name
		self.warehouse = module("_Test FP Warehouse")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_customers_read_their_features_and_no_one_elses(self):
		feature = make_feature(self.implementation, title="Batches", module=self.warehouse, estimated_hours=8)
		other = make_feature(make_implementation().name, title="Elsewhere")
		frappe.set_user(CUSTOMER_USER)
		data = get_features(self.implementation)
		self.assertEqual([f["name"] for f in data["features"]], [feature.name])
		self.assertEqual(data["features"][0]["effort_hours"], 8)
		self.assertFalse(data["can_move"])
		self.assertEqual(get_feature(self.implementation, feature.name)["title"], "Batches")
		self.assertRaises(frappe.PermissionError, get_feature, self.implementation, other.name)
		frappe.set_user(OUTSIDER_USER)
		self.assertRaises(frappe.PermissionError, get_features, self.implementation)

	def test_only_staff_move_cards_and_the_wip_limit_shows(self):
		first = make_feature(self.implementation, title="One", status="In Progress")
		second = make_feature(self.implementation, title="Two", status="Planned")
		frappe.set_user(CUSTOMER_USER)
		self.assertRaises(frappe.PermissionError, set_feature_status, self.implementation, second.name, "In Progress")
		frappe.set_user("Administrator")
		self.assertTrue(get_features(self.implementation)["can_move"])
		result = set_feature_status(self.implementation, second.name, "In Progress")
		self.assertEqual(result["wip"], {"running": 2, "limit": 1, "over": True})
		self.assertEqual(frappe.db.get_value("Implementation Feature", second.name, "status"), "In Progress")
		self.assertRaises(frappe.ValidationError, set_feature_status, self.implementation, first.name, "Somewhere")

	def test_dropping_after_the_baseline_is_recorded_for_the_customer(self):
		feature = make_feature(self.implementation, title="Maybe", status="Agreed")
		create_baseline(self.implementation)
		set_feature_status(self.implementation, feature.name, "Dropped")
		changes = frappe.get_all(
			"Implementation Change", filters={"target_name": feature.name}, fields=["change_type", "status"]
		)
		self.assertEqual([(c.change_type, c.status) for c in changes], [("Scope drop", "Applied – awaiting customer")])

	def test_wbs_rolls_up_by_hours_and_counts_without_hours(self):
		live = make_feature(self.implementation, title="Live", module=self.warehouse, estimated_hours=10, status="Live")
		half = make_feature(self.implementation, title="Half", module=self.warehouse, estimated_hours=30)
		gitlab_issue(half.name, state="closed")
		gitlab_issue(half.name)
		make_feature(self.implementation, title="Gone", module=self.warehouse, estimated_hours=99, status="Dropped")
		wbs = get_wbs(self.implementation)
		warehouse = next(m for m in wbs["modules"] if m["module"] == self.warehouse)
		self.assertEqual({f["title"] for f in warehouse["features"]}, {"Live", "Half"})  # Dropped counts nowhere
		self.assertEqual(warehouse["progress"], 63)  # (100 × 10 + 50 × 30) / 40 = 62.5
		self.assertEqual(warehouse["weight_hours"], 40)
		self.assertTrue(wbs["weighted"])
		# an issue estimate above the feature's hours is the weight
		gitlab_issue(live.name, state="closed", estimate=50)
		self.assertEqual(next(f for f in get_wbs(self.implementation)["modules"][0]["features"] if f["title"] == "Live")["weight_hours"], 50)
		# no hours at all: a plain average
		self.assertEqual(roll_up([(100, 0), (0, 0), (50, 0)]), 50)

	def test_progress_follows_level_without_issues(self):
		make_feature(self.implementation, title="Levels", target_level=4, current_level=1)
		row = get_features(self.implementation)["features"][0]
		self.assertEqual(row["progress"], 25)
