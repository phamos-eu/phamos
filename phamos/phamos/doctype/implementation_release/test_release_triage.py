# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

"""Release triage with both sides' consent (#1986 part 3, through #1971)."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from phamos.phamos.doctype.implementation_baseline.implementation_baseline import (
	create_baseline,
	get_baseline_variance,
)
from phamos.phamos.doctype.implementation_change.implementation_change import (
	AWAITING,
	agree_change,
	propose_change,
)
from phamos.phamos.doctype.implementation_change.test_implementation_change import (
	CUSTOMER_USER,
	_website_user,
)
from phamos.phamos.doctype.implementation_feature.test_implementation_feature import make_feature
from phamos.phamos.doctype.implementation_release.implementation_release import get_triage, preview_triage
from phamos.phamos.doctype.implementation_release.test_implementation_release import (
	FAR,
	NEAR,
	fixed_capacity,
	make_release,
)
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import make_implementation

LATER = add_days(FAR, 30)
CAPACITY = {str(getdate(NEAR)): 10, str(getdate(FAR)): 25, str(getdate(LATER)): 40}


def ranking(release):
	return [row.feature for row in frappe.get_doc("Implementation Release", release).features]


class TestReleaseTriage(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.contact = _website_user(CUSTOMER_USER)

	def setUp(self):
		frappe.set_user("Administrator")
		implementation = frappe.get_doc("Implementation", make_implementation().name)
		implementation.show_on_customer_portal = 1
		implementation.append(
			"stakeholders", {"contact": self.contact, "full_name": "IC Customer", "stakeholder_organisation": "Customer"}
		)
		implementation.save()
		self.implementation = implementation.name
		self.a, self.b, self.c = (
			make_feature(self.implementation, title=title, estimated_hours=hours).name
			for title, hours in (("A", 6), ("B", 6), ("C", 10))
		)
		self.capacity = fixed_capacity(CAPACITY)
		self.capacity.start()
		self.first = make_release(self.implementation, [self.a, self.b], NEAR, title="First").name
		self.second = make_release(self.implementation, [self.c], FAR, title="Second").name

	def tearDown(self):
		self.capacity.stop()
		frappe.set_user("Administrator")

	def propose_as_customer(self, release, change_type, values):
		frappe.set_user(CUSTOMER_USER)
		name = propose_change(self.implementation, "Implementation Release", change_type, values, release)
		frappe.set_user("Administrator")
		return name

	def test_reranking_applies_after_both_agree(self):
		name = self.propose_as_customer(self.first, "Rank", {"ranking": [self.b, self.a]})
		self.assertEqual(ranking(self.first), [self.a, self.b])
		self.assertEqual(json.loads(frappe.db.get_value("Implementation Change", name, "old_values")), {"ranking": [self.a, self.b]})
		self.assertEqual(agree_change(name), "Applied")
		self.assertEqual(ranking(self.first), [self.b, self.a])

	def test_an_agreed_move_leaves_exactly_one_change_record(self):
		create_baseline(self.implementation)
		name = self.propose_as_customer(self.first, "Rank", {"feature": self.b, "to_release": self.second})
		agree_change(name)
		# both releases were saved by the change itself: no extra "awaiting customer" record
		self.assertEqual(
			frappe.get_all("Implementation Change", filters={"implementation": self.implementation}, pluck="name"),
			[name],
		)

	def test_moving_a_feature_to_another_release(self):
		name = self.propose_as_customer(self.first, "Rank", {"feature": self.b, "to_release": self.second, "position": 1})
		agree_change(name)
		self.assertEqual(ranking(self.first), [self.a])
		self.assertEqual(ranking(self.second), [self.b, self.c])
		# the cut line follows: first now fits, second carries B
		self.assertEqual(frappe.db.get_value("Implementation Release", self.first, "fit"), "Green")

	def test_new_target_date(self):
		name = self.propose_as_customer(self.first, "Dates", {"target_date": str(getdate(LATER))})
		agree_change(name)
		self.assertEqual(str(frappe.db.get_value("Implementation Release", self.first, "target_date")), str(getdate(LATER)))

	def test_wrong_proposals_are_refused(self):
		frappe.set_user(CUSTOMER_USER)
		for values in (
			{"ranking": [self.a]},  # not the same features
			{"feature": self.c, "to_release": self.second},  # not in this release
			{"feature": self.a, "to_release": self.first},  # same release
		):
			self.assertRaises(
				frappe.ValidationError, propose_change, self.implementation, "Implementation Release", "Rank", values, self.first
			)
		# malformed payloads get a message, not a server error
		for values in (
			{"ranking": [1, self.a]},
			{"feature": [self.a], "to_release": self.second},
			{"feature": self.a, "to_release": {"name": self.second}},
			{"feature": self.a, "to_release": self.second, "position": "first"},
			{"feature": self.a, "to_release": self.second, "position": 0},
		):
			self.assertRaises(
				frappe.ValidationError, propose_change, self.implementation, "Implementation Release", "Rank", values, self.first
			)
		other = make_release(make_implementation().name, [], FAR, title="Elsewhere").name
		self.assertRaises(
			frappe.ValidationError,
			propose_change,
			self.implementation,
			"Implementation Release",
			"Rank",
			{"feature": self.a, "to_release": other},
			self.first,
		)

	def test_preview_moves_the_cut_line_without_saving(self):
		before = get_triage(self.implementation)
		self.assertEqual([row["fit"] for row in before], ["Red", "Green"])
		frappe.set_user(CUSTOMER_USER)
		preview = preview_triage(
			self.implementation, self.first, "Rank", {"feature": self.b, "to_release": self.second}
		)
		self.assertEqual(preview[self.first]["fit"], "Green")
		self.assertEqual(preview[self.second]["features"][self.b], (6.0, 1))
		frappe.set_user("Administrator")
		self.assertEqual(ranking(self.first), [self.a, self.b])

	def test_direct_edits_of_a_release_after_the_baseline(self):
		create_baseline(self.implementation)
		release = frappe.get_doc("Implementation Release", self.first)
		release.features = release.features[::-1]
		release.target_date = FAR
		release.save()
		changes = {
			row.change_type: row
			for row in frappe.get_all(
				"Implementation Change",
				filters={"target_name": self.first},
				fields=["change_type", "status", "proposed_values"],
			)
		}
		self.assertEqual(set(changes), {"Rank", "Dates"})
		self.assertEqual(changes["Rank"].status, AWAITING)
		self.assertEqual(json.loads(changes["Rank"].proposed_values), {"ranking": [self.b, self.a]})

	def test_baseline_holds_releases_and_shows_their_variance(self):
		create_baseline(self.implementation)
		frappe.db.set_value("Implementation Release", self.second, "target_date", LATER)
		name = self.propose_as_customer(self.first, "Rank", {"feature": self.b, "to_release": self.second})
		agree_change(name)
		variance = {row["name"]: row for row in get_baseline_variance(self.implementation)["releases"]}
		self.assertEqual(variance[self.second]["target_shift_days"], 30)
		self.assertEqual(variance[self.second]["features_added"], [self.b])
		self.assertEqual(variance[self.first]["features_removed"], [self.b])

	def test_released_or_cancelled_releases_are_not_replanned(self):
		for status in ("Released", "Cancelled"):
			frappe.db.set_value("Implementation Release", self.first, "status", status)
			for change_type, values in (("Dates", {"target_date": str(getdate(LATER))}), ("Rank", {"ranking": [self.b, self.a]})):
				self.assertRaises(
					frappe.ValidationError,
					propose_change,
					self.implementation,
					"Implementation Release",
					change_type,
					values,
					self.first,
				)

	def test_values_the_target_refuses_are_refused_at_once(self):
		frappe.set_user(CUSTOMER_USER)
		for change_type, values in (
			("Dates", {"target_date": "not a date"}),
			("Dates", {"target_date": ["2027-01-01"]}),
		):
			self.assertRaises(
				frappe.ValidationError,
				propose_change,
				self.implementation,
				"Implementation Release",
				change_type,
				values,
				self.first,
			)
		self.assertRaises(
			frappe.ValidationError,
			propose_change,
			self.implementation,
			"Implementation",
			"WIP limit",
			{"max_parallel_features": -1},
			self.implementation,
		)
		frappe.db.set_value("Implementation Feature", self.a, "planned_start", "2027-03-01")
		self.assertRaises(
			frappe.ValidationError,
			propose_change,
			self.implementation,
			"Implementation Feature",
			"Dates",
			{"target_date": "2027-01-01"},
			self.a,
		)
		self.assertFalse(frappe.get_all("Implementation Change", filters={"implementation": self.implementation}))

	def test_a_direct_change_of_a_releases_features_is_a_scope_change(self):
		create_baseline(self.implementation)
		release = frappe.get_doc("Implementation Release", self.first)
		release.remove(release.features[1])
		release.save()
		change = frappe.get_all(
			"Implementation Change",
			filters={"target_name": self.first},
			fields=["change_type", "proposed_values"],
		)
		self.assertEqual([row.change_type for row in change], ["Scope change"])
		self.assertEqual(json.loads(change[0].proposed_values), {"features": [self.a]})
