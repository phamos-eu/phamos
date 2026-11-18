# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phamos.doctype.implementation_feature.implementation_feature import take_over_from_sales
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import make_implementation


def make_feature(implementation=None, opportunity=None, **values):
	return frappe.get_doc(
		{
			"doctype": "Implementation Feature",
			"title": values.pop("title", "Batch numbers on goods receipt"),
			"implementation": implementation,
			"opportunity": opportunity,
			**values,
		}
	).insert(ignore_permissions=True)


class TestImplementationFeature(FrappeTestCase):
	def setUp(self):
		self.implementation = make_implementation()

	def test_needs_an_implementation_or_an_opportunity(self):
		self.assertRaises(frappe.ValidationError, make_feature)

	def test_customer_comes_from_the_implementation(self):
		feature = make_feature(self.implementation.name)
		self.assertEqual(feature.customer, self.implementation.customer)

	def test_levels_stay_on_the_module_scale(self):
		self.assertRaises(frappe.ValidationError, make_feature, self.implementation.name, target_level=7)
		self.assertRaises(
			frappe.ValidationError, make_feature, self.implementation.name, target_level=3, current_level=4
		)
		# beyond the target only once it is live
		make_feature(self.implementation.name, target_level=3, current_level=4, status="Live")

	def test_target_date_after_planned_start(self):
		self.assertRaises(
			frappe.ValidationError,
			make_feature,
			self.implementation.name,
			planned_start="2026-12-01",
			target_date="2026-11-01",
		)

	def test_progress_history_on_status_and_level_changes(self):
		feature = make_feature(self.implementation.name, target_level=4, current_level=1)
		self.assertEqual(len(feature.progress), 1)
		feature.description = "only text"
		feature.save()
		self.assertEqual(len(feature.progress), 1)
		feature.current_level = 2
		feature.status = "In Progress"
		feature.save()
		self.assertEqual(len(feature.progress), 2)
		self.assertEqual((feature.progress[-1].status, feature.progress[-1].level), ("In Progress", 2))

	def test_changed_definition_of_done_needs_a_new_agreement(self):
		feature = make_feature(
			self.implementation.name, definition_of_done="Batches selectable", dod_agreed_on="2026-11-18"
		)
		feature.definition_of_done = "Batches selectable and printed"
		feature.save()
		self.assertIsNone(feature.dod_agreed_on)
		# changing text and agreement together keeps the new agreement
		feature.definition_of_done = "Batches selectable, printed and on the pick list"
		feature.dod_agreed_on = "2026-11-19"
		feature.save()
		self.assertEqual(str(feature.dod_agreed_on), "2026-11-19")

	def test_dependencies_same_implementation_and_no_loops(self):
		first = make_feature(self.implementation.name, title="First")
		second = make_feature(self.implementation.name, title="Second", depends_on=[{"feature": first.name}])
		first.append("depends_on", {"feature": second.name})
		self.assertRaises(frappe.ValidationError, first.save)

		other = make_feature(make_implementation().name, title="Elsewhere")
		self.assertRaises(
			frappe.ValidationError,
			make_feature,
			self.implementation.name,
			title="Mixed",
			depends_on=[{"feature": other.name}],
		)

	def test_suggested_progress_from_gitlab_issues(self):
		feature = make_feature(self.implementation.name)
		self.assertIsNone(feature.suggested_progress)
		for index, state in enumerate(("closed", "opened", "closed", "closed")):
			frappe.get_doc(
				{
					"doctype": "GitLab Issue",
					"name": f"_Test IF {feature.name} {index}",
					"issue_id": f"9{index}",
					"title": "work",
					"state": state,
					"implementation_feature": feature.name,
				}
			).db_insert()
		self.assertEqual(feature.suggested_progress, 75)

	def test_take_over_from_sales(self):
		customer = self.implementation.customer
		opportunity = f"_Test IF Opp {frappe.generate_hash(length=6)}"
		frappe.get_doc(
			{"doctype": "Opportunity", "name": opportunity, "opportunity_from": "Customer", "party_name": customer}
		).db_insert()
		quotation = f"_Test IF Quo {frappe.generate_hash(length=6)}"
		frappe.get_doc(
			{"doctype": "Quotation", "name": quotation, "opportunity": opportunity, "party_name": customer}
		).db_insert()
		order = f"_Test IF SO {frappe.generate_hash(length=6)}"
		frappe.get_doc(
			{
				"doctype": "Sales Order",
				"name": order,
				"customer": customer,
				"custom_implementation": self.implementation.name,
				"docstatus": 1,
			}
		).db_insert()
		frappe.get_doc(
			{
				"doctype": "Sales Order Item",
				"parent": order,
				"parenttype": "Sales Order",
				"parentfield": "items",
				"idx": 1,
				"item_code": "_Test Item",
				"prevdoc_docname": quotation,
			}
		).db_insert()

		in_sales = make_feature(opportunity=opportunity, source="Sales", title="Configured in sales")
		self.assertEqual(in_sales.customer, customer)
		lost = f"_Test IF Lost {frappe.generate_hash(length=6)}"
		frappe.get_doc(
			{"doctype": "Opportunity", "name": lost, "opportunity_from": "Customer", "party_name": customer}
		).db_insert()
		not_won = make_feature(opportunity=lost, source="Sales", title="Not won")

		moved = take_over_from_sales(self.implementation.name)
		self.assertEqual(moved, [in_sales.name])
		in_sales.reload()
		self.assertEqual((in_sales.implementation, in_sales.source), (self.implementation.name, "Sales"))
		self.assertEqual(take_over_from_sales(self.implementation.name), [])
		self.assertFalse(frappe.db.get_value("Implementation Feature", not_won.name, "implementation"))
