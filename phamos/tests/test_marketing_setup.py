"""The "Event Ticketing" role: only what an order needs, untouched permission copies removed, drift reported
(phamos/phamos#1708). bench --site <site> run-tests --module phamos.tests.test_marketing_setup
"""

import io
from contextlib import redirect_stdout
from unittest.mock import patch

import frappe
from frappe.permissions import add_permission, setup_custom_perms
from frappe.tests.utils import FrappeTestCase

from phamos.marketing import setup, ticketing
from phamos.patches.v1_0 import remove_unneeded_ticketing_permissions
from phamos.tests.marketing_fixtures import BILLING, CONTACT, as_guest, ensure_company, make_event


def clear(*doctypes):
	for doctype in doctypes:
		frappe.clear_cache(doctype=doctype)
	frappe.clear_cache(user=setup.TICKETING_USER)


@patch("frappe.enqueue")
class TestTicketingRole(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_company()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("ticketing_role_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="ticketing_role_test")
		clear(*setup.FORMER_TICKETING_DOCTYPES, *setup.TICKETING_READ, *setup.TICKETING_SELECT)

	def test_guest_orders_work_with_the_reduced_role(self, enqueue):
		setup.ensure_ticketing_user()
		frappe.db.delete("Custom DocPerm", {"role": setup.TICKETING_ROLE,
			"parent": ["not in", setup.TICKETING_READ + setup.TICKETING_SELECT]})
		clear(*setup.FORMER_TICKETING_DOCTYPES)
		self.assertEqual(set(frappe.get_all("Custom DocPerm", filters={"role": setup.TICKETING_ROLE}, pluck="parent")),
			{"Item", "Account"})
		paid = make_event("Role Paid Event")
		free = make_event("Role Free Event", paid=False)
		with as_guest():
			order = ticketing.register_attendees(paid.name, CONTACT, companions=[],
				billing_data={**BILLING, "is_company": 1, "company": "Role Test GmbH"})
			booking = ticketing.register_attendees(free.name, {**CONTACT, "email": "free.role@ticket.example"}, companions=[])
		self.assertEqual(frappe.db.get_value("Sales Order", order["reference"], "docstatus"), 1)
		self.assertEqual(booking["reference_doctype"], "Attendee")

	def copy_with_role(self, doctype):
		"""The state before #1708: the standard permissions copied, plus the role's read row."""
		frappe.db.delete("Custom DocPerm", {"parent": doctype})
		setup_custom_perms(doctype)
		add_permission(doctype, setup.TICKETING_ROLE, permlevel=0, ptype="read")
		clear(doctype)

	def run_patch(self):
		with redirect_stdout(io.StringIO()) as out:
			remove_unneeded_ticketing_permissions.execute()
		return out.getvalue()

	def test_patch_removes_an_untouched_copy(self, enqueue):
		self.copy_with_role("UOM")
		self.assertIn("UOM: removed 1 Event Ticketing row(s) and the untouched copy", self.run_patch())
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": "UOM"}))
		self.assertEqual(self.run_patch().count("UOM"), 0)  # a second run changes nothing

	def test_patch_keeps_a_customised_copy(self, enqueue):
		self.copy_with_role("Currency")
		row = frappe.get_all("Custom DocPerm", filters={"parent": "Currency", "role": ["!=", setup.TICKETING_ROLE]},
			pluck="name", limit=1)[0]
		frappe.db.set_value("Custom DocPerm", row, "export", 1 - (frappe.db.get_value("Custom DocPerm", row, "export") or 0))
		self.assertIn("Currency: removed 1 Event Ticketing row(s); kept", self.run_patch())
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": "Currency", "role": setup.TICKETING_ROLE}))
		self.assertTrue(frappe.db.exists("Custom DocPerm", {"parent": "Currency"}))

	def test_drift_of_item_permissions_is_reported(self, enqueue):
		self.copy_with_role("Item")
		with patch("frappe.log_error") as log_error:
			setup.report_permission_drift()
		self.assertFalse([c for c in log_error.call_args_list if "Item" in c.kwargs.get("title", "")])
		standard = frappe.get_all("DocPerm", filters={"parent": "Item"}, pluck="name", limit=1)[0]
		frappe.db.set_value("DocPerm", standard, "export", 1 - (frappe.db.get_value("DocPerm", standard, "export") or 0))
		with patch("frappe.log_error") as log_error:
			setup.report_permission_drift()
		self.assertEqual(len([c for c in log_error.call_args_list if "Item" in c.kwargs.get("title", "")]), 1)
