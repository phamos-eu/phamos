"""Sales Order → Sales Invoice → payment as seen on the Attendees; Opportunities on demand; backfill.

bench --site <site> run-tests --module phamos.tests.test_marketing_billing
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.marketing import billing, crm, ticketing
from phamos.marketing.api import create_customers, create_opportunities, create_sales_invoices, create_sales_orders
from phamos.tests.marketing_fixtures import BILLING, as_guest, ensure_company, make_attendee, make_event


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

	def web_order(self):
		with as_guest():
			result = ticketing.register_attendees(self.event.name, {"full_name": "Bill Buyer", "email": "bill@billing.example"},
				companions=[{"full_name": "Colleague One", "email": "colleague@billing.example"}],
				billing_data={**BILLING, "full_name": "Bill Buyer", "email": "bill@billing.example",
					"is_company": 1, "company": "Billing Test GmbH"})
		return result["reference"]

	def test_invoice_payment_and_cancel(self, enqueue):
		so_name = self.web_order()
		self.assertEqual(statuses(sales_order=so_name), {"Ordered"})
		invoices = create_sales_invoices(names=frappe.get_all("Attendee", filters={"sales_order": so_name}, pluck="name"),
			submit=1)["sales_invoices"]
		self.assertEqual(len(invoices), 1)
		si = frappe.get_doc("Sales Invoice", invoices[0])
		self.assertEqual(si.grand_total, 238)
		self.assertEqual(statuses(sales_order=so_name), {"Invoiced"})
		self.assertEqual(set(frappe.get_all("Attendee", filters={"sales_order": so_name}, pluck="sales_invoice")), {si.name})

		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		pe = get_payment_entry("Sales Invoice", si.name)
		pe.reference_no, pe.reference_date = "TEST", frappe.utils.nowdate()
		pe.insert()
		pe.submit()
		self.assertEqual(statuses(sales_order=so_name), {"Paid"})
		pe.cancel()
		self.assertEqual(statuses(sales_order=so_name), {"Invoiced"})
		si.reload()
		si.cancel()
		self.assertEqual(statuses(sales_order=so_name), {"Ordered"})
		frappe.get_doc("Sales Order", so_name).cancel()
		self.assertEqual(statuses(order_reference=so_name), {"Pending"})

	def test_opportunities_on_demand(self, enqueue):
		so_name = self.web_order()
		names = frappe.get_all("Attendee", filters={"sales_order": so_name}, pluck="name", order_by="creation asc")
		nobody = make_attendee(self.event.name, None, "No", "Email")
		result = create_opportunities(names + [nobody.name])
		self.assertEqual(len(result["opportunities"]), 2)
		self.assertEqual(result["skipped"], [nobody.name])
		opportunity = frappe.get_doc("Opportunity", frappe.db.get_value("Attendee", names[0], "opportunity"))
		self.assertEqual((opportunity.opportunity_from, opportunity.source), ("Customer", "Event"))
		self.assertEqual(opportunity.campaign, frappe.db.get_value("Marketing Content", self.event.name, "campaign"))
		self.assertEqual(create_opportunities(names)["skipped"], names)  # never twice

	def test_backfill_customers_and_orders(self, enqueue):
		buyer = make_attendee(self.event.name, "imported@backfill.example", "Imported", "Buyer",
			company_name="Backfill GmbH", is_buyer=1, source="Import")
		buyer.db_set("order_reference", "SHEET-1")
		mate = make_attendee(self.event.name, "mate@backfill.example", "Team", "Mate", source="Import")
		mate.db_set("order_reference", "SHEET-1")
		crm.link_attendee(buyer.name)
		customer = create_customers([buyer.name, mate.name])["results"][0]["customer"]
		self.assertEqual(frappe.db.get_value("Customer", customer, "customer_type"), "Company")
		orders = create_sales_orders([buyer.name, mate.name], submit=1)["sales_orders"]
		self.assertEqual(len(orders), 1)
		so = frappe.get_doc("Sales Order", orders[0])
		self.assertEqual((so.customer, len(so.items), so.docstatus), (customer, 2, 1))
		self.assertEqual(statuses(sales_order=so.name), {"Ordered"})
		self.assertEqual(set(frappe.get_all("Attendee", filters={"sales_order": so.name}, pluck="order_reference")), {"SHEET-1"})

	def test_price_summary(self, enqueue):
		self.assertIn("Regular", billing.price_summary(self.event))
		self.assertIn("119", self.event.ticket_price_summary)

	def test_event_order_print_format(self, enqueue):
		so = frappe.get_doc("Sales Order", self.web_order())
		self.assertIn("format=Event+Order", billing.order_pdf_url(so, "de"))
		lang = frappe.local.lang
		try:
			frappe.local.lang = "de"
			html = frappe.get_print("Sales Order", so.name, billing.ORDER_PRINT_FORMAT, as_pdf=0, no_letterhead=1)
		finally:
			frappe.local.lang = lang
		for part in ["eo-sender", "Bestellung: Billing Test Event", so.name, "Test Venue, Reutlingen", "bill@billing.example",
				"Billing Test GmbH<br>Bill Buyer<br>", "Colleague One", "Einzelpreis", "Netto", "MwSt. 19 %", "Zahlung per Rechnung", "footer-html"]:
			self.assertIn(part, html)
		self.assertIn("238", html)
