# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""A Lead's Connections show its Event Ticket Orders and Attendees (phamos/phamos#2215)."""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestLeadDashboard(FrappeTestCase):
	def test_events_group_links_through_lead_field(self):
		data = frappe.get_meta("Lead").get_dashboard_data()

		events = [group for group in data.transactions if "Event Ticket Order" in group.get("items", [])]
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0]["items"], ["Event Ticket Order", "Attendee"])
		# ERPNext's own groups stay.
		self.assertIn("Opportunity", [item for group in data.transactions for item in group.get("items", [])])

		# The dashboard counts by data.fieldname, so both doctypes must link to Lead through it.
		for doctype in ("Event Ticket Order", "Attendee"):
			field = frappe.get_meta(doctype).get_field(data.fieldname)
			self.assertEqual((field.fieldtype, field.options), ("Link", "Lead"), doctype)
