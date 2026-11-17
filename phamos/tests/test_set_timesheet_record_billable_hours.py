# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Patch set_timesheet_record_billable_hours (#1746)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.patches.v1_0.set_timesheet_record_billable_hours import execute


def _record_before_migration(percent_billable, actual_time=7200, docstatus=1):
	"""A Timesheet Record row as it stood before the patch: no Billable Hours stored yet.

	Inserted directly, without validation, so it can hold values the form no longer allows.
	"""
	doc = frappe.new_doc("Timesheet Record")
	doc.name = f"TR-PATCH-{frappe.generate_hash(length=8)}"
	doc.percent_billable = percent_billable
	doc.actual_time = actual_time
	doc.billable_hours = 0
	doc.docstatus = docstatus
	doc.db_insert()
	return doc.name


def _billable_hours(name):
	return frappe.db.get_value("Timesheet Record", name, "billable_hours")


class TestSetTimesheetRecordBillableHours(FrappeTestCase):
	def test_submitted_record_gets_actual_time_times_percent_billable(self):
		name = _record_before_migration("50", actual_time=7200)

		execute()

		self.assertAlmostEqual(_billable_hours(name), 1.0)

	def test_percent_billable_internal_counts_as_zero(self):
		# "Internal" was a Percent Billable option from d61c0d0a until it was reverted in 369670d8.
		internal = _record_before_migration("Internal")
		billable = _record_before_migration("100", actual_time=3600)

		execute()

		self.assertEqual(_billable_hours(internal), 0)
		self.assertAlmostEqual(_billable_hours(billable), 1.0)

	def test_empty_percent_billable_counts_as_zero(self):
		name = _record_before_migration("")

		execute()

		self.assertEqual(_billable_hours(name), 0)

	def test_draft_record_is_left_alone(self):
		name = _record_before_migration("100", docstatus=0)

		execute()

		self.assertEqual(_billable_hours(name), 0)

	def test_value_add_billing_is_switched_on(self):
		frappe.db.set_single_value("Phamos Settings", "value_add_in_billing", 0)

		execute()

		self.assertEqual(frappe.db.get_single_value("Phamos Settings", "value_add_in_billing"), 1)
