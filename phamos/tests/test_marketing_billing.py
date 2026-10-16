"""Quotation → Sales Order → Sales Invoice → payment, as seen on the Attendees.

bench --site <site> run-tests --module phamos.tests.test_marketing_billing
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.marketing import billing, crm, ticketing
from phamos.marketing.api import create_customers, create_sales_orders
from phamos.tests.marketing_fixtures import CONSENTS, as_guest, ensure_company, make_attendee, make_event


def statuses(**filters):
	return set(frappe.get_all("Attendee", filters=filters, pluck="payment_status"))


@patch("frappe.enqueue")
class TestBilling(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_company()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("billing_test")
		self.event = make_event("Billing Test Event")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="billing_test")

	def web_order(self, company=""):
		billing_data = {"full_name": "Bill Buyer", "email": "bill@billing.example", "company": company,
			"is_company": 1 if company else 0, "address_line1": "Weg 2", "postcode": "70173", "city": "Stuttgart",
			"country": "Germany"}
		with as_guest():
			result = ticketing.register_attendees(self.event.name, [
				{"full_name": "Bill Buyer", "email": "bill@billing.example"},
				{"full_name": "Colleague One", "email": "colleague@billing.example"}],
				billing_data=billing_data, consents=CONSENTS)
		return result["reference"]

	def test_quotation_to_paid_invoice(self, enqueue):
		quotation = self.web_order(company="Billing Test GmbH")
		so = billing.make_sales_order_from_quotation(quotation, submit=True)
		customer = frappe.get_doc("Customer", so.customer)
		self.assertEqual(customer.customer_type, "Company")
		lead = frappe.db.get_value("Quotation", quotation, "party_name")
		self.assertEqual(frappe.db.get_value("Lead", lead, "status"), "Converted")
		self.assertEqual(statuses(quotation=quotation), {"Ordered"})
		self.assertEqual(len(frappe.get_all("Attendee", filters={"sales_order": so.name})), 2)
		for contact in frappe.get_all("Attendee", filters={"quotation": quotation}, pluck="contact"):
			self.assertTrue(frappe.db.exists("Dynamic Link", {"parent": contact, "link_doctype": "Customer",
				"link_name": customer.name}))

		si = billing.make_sales_invoice(so.name, submit=True)
		self.assertEqual(statuses(sales_order=so.name), {"Invoiced"})
		self.assertEqual(set(frappe.get_all("Attendee", filters={"sales_order": so.name}, pluck="sales_invoice")), {si.name})

		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		pe = get_payment_entry("Sales Invoice", si.name)
		pe.reference_no, pe.reference_date = "TEST", frappe.utils.nowdate()
		pe.insert()
		pe.submit()
		self.assertEqual(statuses(sales_order=so.name), {"Paid"})
		pe.cancel()
		self.assertEqual(statuses(sales_order=so.name), {"Invoiced"})
		si.reload()
		si.cancel()
		self.assertEqual(statuses(sales_order=so.name), {"Ordered"})

	def test_private_buyer_becomes_individual_customer(self, enqueue):
		quotation = self.web_order()
		so = billing.make_sales_order_from_quotation(quotation)
		self.assertEqual(frappe.db.get_value("Customer", so.customer, "customer_type"), "Individual")

	def test_quotation_can_be_assigned_to_an_existing_customer(self, enqueue):
		from phamos.tests.marketing_fixtures import make_customer

		existing = make_customer("Existing Billing Customer GmbH")
		quotation = self.web_order(company="Existing Billing Customer")
		so = billing.make_sales_order_from_quotation(quotation, customer=existing)
		self.assertEqual(so.customer, existing)
		self.assertFalse(frappe.db.exists("Customer", {"customer_name": "Existing Billing Customer"}))

	def test_cancelled_quotation_cancels_open_attendees(self, enqueue):
		quotation = self.web_order()
		frappe.get_doc("Quotation", quotation).cancel()
		self.assertEqual(statuses(quotation=quotation), {"Cancelled"})

	def test_backfill_customers_and_orders(self, enqueue):
		buyer = make_attendee(self.event.name, "imported@backfill.example", "Imported", "Buyer",
			company_name="Backfill GmbH", is_buyer=1, source="Import")
		buyer.db_set("order_reference", "SHEET-1")
		mate = make_attendee(self.event.name, "mate@backfill.example", "Team", "Mate", source="Import")
		mate.db_set("order_reference", "SHEET-1")
		crm.link_attendee(buyer.name)
		result = create_customers([buyer.name, mate.name])
		customer = result["results"][0]["customer"]
		self.assertEqual(frappe.db.get_value("Customer", customer, "customer_type"), "Company")
		orders = create_sales_orders([buyer.name, mate.name], submit=1)["sales_orders"]
		self.assertEqual(len(orders), 1)
		so = frappe.get_doc("Sales Order", orders[0])
		self.assertEqual((so.customer, len(so.items), so.docstatus), (customer, 2, 1))
		self.assertEqual(statuses(order_reference="SHEET-1"), {"Ordered"})
