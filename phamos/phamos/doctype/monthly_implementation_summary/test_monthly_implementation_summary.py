# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

PROJECT = "_T-MIS-PROJ"


class TestMonthlyImplementationSummary(FrappeTestCase):
	"""Timesheet -> Delivery Note stamping when one MIS gets several Delivery Notes.

	Records are written with db_insert (no validation) so the tests only need the rows the
	stamping reads; every test is rolled back."""

	def tearDown(self):
		frappe.db.rollback()

	def _make_mis(self, billable_hours, projects=None):
		projects = projects or [PROJECT] * len(billable_hours)
		names = []
		for i, _hours in enumerate(billable_hours, start=1):
			name = f"_T-MIS-TS-{i}"
			frappe.get_doc({"doctype": "Timesheet", "name": name}).db_insert()
			names.append(name)
		mis = frappe.get_doc({
			"doctype": "Monthly Implementation Summary",
			"name": "_T-MIS-1",
			"timesheets_table": [
				{"timesheet": ts, "project": project, "billable_hours": hours}
				for ts, hours, project in zip(names, billable_hours, projects)
			],
		})
		mis.db_insert()
		mis.set_parent_in_children()
		for row in mis.timesheets_table:
			row.db_insert()
		return mis, names

	def _deliver(self, mis, dn_name, hours, docstatus=0):
		"""What _create_dn_for_so_hours does once the Delivery Note is inserted: the MIS Delivery Note
		row is written through another MIS instance, then the (now stale) MIS stamps its Timesheets."""
		frappe.get_doc({"doctype": "Delivery Note", "name": dn_name, "docstatus": docstatus}).db_insert()
		frappe.get_doc({
			"doctype": "MIS Delivery Note",
			"name": f"{dn_name}-row",
			"parent": mis.name,
			"parenttype": "Monthly Implementation Summary",
			"parentfield": "mis_delivery_notes",
			"delivery_note": dn_name,
			"hours": hours,
			"project": PROJECT,
			"status": "Draft" if docstatus == 0 else "To Bill",
		}).db_insert()
		mis._stamp_timesheets_for_delivered_hours(dn_name, hours, PROJECT)

	def _linked_dns(self, timesheets):
		return [frappe.db.get_value("Timesheet", ts, "custom_delivery_note") for ts in timesheets]

	def test_one_draft_dn_per_sales_order_links_every_timesheet(self):
		# MIS-2026-0075: 2 h + 1 h + 1 h of timesheets, one Delivery Note per Sales Order in one go.
		mis, ts = self._make_mis([2, 1, 1])
		self._deliver(mis, "_T-DN-1", 2)
		self._deliver(mis, "_T-DN-2", 1)
		self._deliver(mis, "_T-DN-3", 1)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1", "_T-DN-2", "_T-DN-3"])

	def test_each_dn_gets_timesheets_matching_its_hours(self):
		# MIS-2026-0001: Delivery Notes of 1 h, 2 h, 1 h over timesheets of 2 h, 1 h, 1 h.
		mis, ts = self._make_mis([2, 1, 1])
		self._deliver(mis, "_T-DN-1", 1)
		self._deliver(mis, "_T-DN-2", 2)
		self._deliver(mis, "_T-DN-3", 1)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-2", "_T-DN-1", "_T-DN-3"])

	def test_second_dn_while_first_is_draft_links_remaining_timesheet(self):
		# MIS-2026-0074: 2 h delivered and left in Draft, then the remaining 0.5 h.
		mis, ts = self._make_mis([1, 1, 0.5])
		self._deliver(mis, "_T-DN-1", 2)
		self._deliver(mis, "_T-DN-2", 0.5)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1", "_T-DN-1", "_T-DN-2"])

	def test_second_dn_after_first_is_submitted_links_remaining_timesheet(self):
		mis, ts = self._make_mis([1, 1, 0.5])
		self._deliver(mis, "_T-DN-1", 2, docstatus=1)
		self._deliver(mis, "_T-DN-2", 0.5)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1", "_T-DN-1", "_T-DN-2"])

	def test_partial_delivery_leaves_undelivered_timesheet_unlinked(self):
		mis, ts = self._make_mis([1, 1, 0.5])
		self._deliver(mis, "_T-DN-1", 2)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1", "_T-DN-1", None])

	def test_timesheets_without_billable_hours_are_linked(self):
		# MIS-2026-0072 / MIS-October-0016: 0-billable timesheets stayed without a Delivery Note.
		mis, ts = self._make_mis([1, 1, 0.5, 0, 0])
		self._deliver(mis, "_T-DN-1", 2.5)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1"] * 5)

	def test_timesheets_without_billable_hours_of_other_projects_are_linked(self):
		# A project with no billable hours never gets a Delivery Note of its own.
		mis, ts = self._make_mis([1, 0, 0.5], [PROJECT, "_T-MIS-PROJ-0H", "_T-MIS-PROJ-OTHER"])
		self._deliver(mis, "_T-DN-1", 1)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1", "_T-DN-1", None])

	def test_linked_timesheet_without_billable_hours_keeps_its_dn(self):
		mis, ts = self._make_mis([1, 1, 0])
		self._deliver(mis, "_T-DN-1", 1)
		self._deliver(mis, "_T-DN-2", 1)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1", "_T-DN-2", "_T-DN-1"])

	def test_timesheet_longer_than_dn_is_linked_to_first_dn(self):
		mis, ts = self._make_mis([4])
		self._deliver(mis, "_T-DN-1", 2)
		self._deliver(mis, "_T-DN-2", 2)
		self.assertEqual(self._linked_dns(ts), ["_T-DN-1"])
