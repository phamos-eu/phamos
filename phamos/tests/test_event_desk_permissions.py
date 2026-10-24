"""Desk actions on Attendees check each row and run with the user's own rights (phamos/phamos#1709).

bench --site <site> run-tests --module phamos.tests.test_event_desk_permissions
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from phamos.marketing import api, billing
from phamos.tests.marketing_fixtures import ensure_company, make_attendee, make_customer, make_event, make_ticket_item

LIMITED = "desk-limited@ticket.example"


@patch("frappe.enqueue")
class TestEventDeskPermissions(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_company()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("desk_permissions_test")
		if not frappe.db.exists("User", LIMITED):
			frappe.get_doc({"doctype": "User", "email": LIMITED, "first_name": "Desk Limited", "send_welcome_email": 0,
				"roles": [{"role": "Website Manager"}]}).insert(ignore_permissions=True)  # Attendee write, no CRM rights
		self.event = make_event("Desk Permission Event", paid=False)
		self.attendee = make_attendee(self.event.name, "desk.person@ticket.example")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="desk_permissions_test")
		frappe.clear_cache(user=LIMITED)

	def test_link_to_crm_needs_contact_and_lead_rights(self, enqueue):
		frappe.set_user(LIMITED)
		self.assertRaises(frappe.PermissionError, api.link_to_crm, [self.attendee.name], create=1)
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.exists("Contact Email", {"email_id": "desk.person@ticket.example"}))
		self.assertFalse(frappe.db.exists("Lead", {"email_id": "desk.person@ticket.example"}))

	def test_link_to_crm_needs_read_on_the_customer(self, enqueue):
		customer = make_customer("Desk Permission Kunde AG")
		frappe.set_user(LIMITED)
		self.assertRaises(frappe.PermissionError, api.link_to_crm, [self.attendee.name], customer=customer)
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.get_value("Attendee", self.attendee.name, "customer"))
		self.assertRaises(frappe.ValidationError, api.link_to_crm, [self.attendee.name], customer="No Such Customer")

	def test_sales_orders_need_the_users_own_rights(self, enqueue):
		frappe.set_user(LIMITED)
		self.assertRaises(frappe.PermissionError, api.create_sales_orders, [self.attendee.name])

	def test_rows_outside_the_users_permissions_are_refused(self, enqueue):
		other = make_event("Desk Permission Other Event", paid=False)
		frappe.get_doc({"doctype": "User Permission", "user": LIMITED, "allow": "Marketing Content",
			"for_value": other.name, "apply_to_all_doctypes": 1}).insert(ignore_permissions=True)
		frappe.clear_cache(user=LIMITED)
		frappe.set_user(LIMITED)
		self.assertRaises(frappe.PermissionError, api.set_attendance, [self.attendee.name], "Attended")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Attendee", self.attendee.name, "status"), "Registered")

	def test_invoices_only_for_event_orders(self, enqueue):
		so = frappe.new_doc("Sales Order")
		so.customer = make_customer("Desk Permission Order AG")
		so.company = billing.default_company()
		so.transaction_date = so.delivery_date = nowdate()
		so.append("items", {"item_code": make_ticket_item(), "qty": 1, "rate": 10, "delivery_date": nowdate()})
		so.insert()
		so.submit()
		result = api.create_sales_invoices(sales_orders=[so.name], submit=0)
		self.assertEqual((result["sales_invoices"], result["skipped"]), ([], [so.name]))
