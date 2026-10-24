"""Sales Order → Sales Invoice → payment as seen on the Attendees; Opportunities on demand; backfill.

bench --site <site> run-tests --module phamos.tests.test_marketing_billing
"""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.marketing import billing, crm, ticketing
from phamos.marketing.api import create_customers, create_opportunities, create_sales_invoices, create_sales_orders
from phamos.tests.marketing_fixtures import BILLING, as_guest, ensure_company, make_attendee, make_customer, make_event


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

	# --- credit notes (phamos/phamos#1706) ------------------------------------------------------------

	def invoice(self, so_name):
		names = frappe.get_all("Attendee", filters={"sales_order": so_name}, pluck="name")
		return frappe.get_doc("Sales Invoice", create_sales_invoices(names=names, submit=1)["sales_invoices"][0])

	def pay(self, si):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		pe = get_payment_entry("Sales Invoice", si.name)
		pe.reference_no, pe.reference_date = "TEST", frappe.utils.nowdate()
		pe.insert()
		pe.submit()

	def credit_note(self, si, lines=None, submit=True):
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		cn = make_sales_return(si.name)
		if lines is not None:
			cn.items = cn.items[:lines]
		cn.insert()
		if submit:
			cn.submit()
		return cn

	def rows(self, so_name):
		return {r.sales_order_item: (r.sales_invoice, r.payment_status) for r in frappe.get_all("Attendee",
			filters={"sales_order": so_name}, fields=["sales_order_item", "sales_invoice", "payment_status"])}

	def test_partial_credit_note_on_a_paid_invoice(self, enqueue):
		so_name = self.web_order()
		si = self.invoice(so_name)
		self.pay(si)
		cn = self.credit_note(si, lines=1)
		credited_line = cn.items[0].so_detail
		for line, (invoice, status) in self.rows(so_name).items():
			self.assertEqual(invoice, si.name)  # never the credit note
			self.assertEqual(status, "Credited" if line == credited_line else "Paid")

	def test_full_credit_then_a_new_invoice(self, enqueue):
		so_name = self.web_order()
		si = self.invoice(so_name)
		self.credit_note(si)
		self.assertEqual(set(self.rows(so_name).values()), {(si.name, "Credited")})
		# The usual correction: a credit note, then a new invoice for the same order lines (a copy of the original).
		corrected = frappe.copy_doc(si)
		corrected.insert()
		corrected.reload()
		corrected.submit()
		self.assertEqual(set(self.rows(so_name).values()), {(corrected.name, "Invoiced")})

	def test_cancelled_credit_note_restores_the_invoice(self, enqueue):
		so_name = self.web_order()
		si = self.invoice(so_name)
		cn = self.credit_note(si)
		cn.cancel()
		self.assertEqual(set(self.rows(so_name).values()), {(si.name, "Invoiced")})

	def test_draft_credit_note_changes_nothing(self, enqueue):
		so_name = self.web_order()
		si = self.invoice(so_name)
		self.pay(si)
		self.credit_note(si, submit=False)
		self.assertEqual(set(self.rows(so_name).values()), {(si.name, "Paid")})

	def test_invoice_hook_runs_only_on_change(self, enqueue):
		# Before: on_submit and on_change, three runs per submit. on_change alone runs twice, because ERPNext's
		# set_status writes the status with db_set during submit; the handler is idempotent.
		so_name = self.web_order()
		names = frappe.get_all("Attendee", filters={"sales_order": so_name}, pluck="name")
		si = frappe.get_doc("Sales Invoice", create_sales_invoices(names=names, submit=0)["sales_invoices"][0])
		with patch.object(billing, "on_sales_invoice_change", wraps=billing.on_sales_invoice_change) as hook:
			si.submit()
		self.assertEqual(hook.call_count, 2)
		self.assertEqual(set(self.rows(so_name).values()), {(si.name, "Invoiced")})

	def test_daily_sync_matches_the_hooks(self, enqueue):
		so_name = self.web_order()
		si = self.invoice(so_name)
		self.pay(si)
		expected = self.rows(so_name)
		frappe.db.set_value("Attendee", {"sales_order": so_name}, "payment_status", "Invoiced")
		billing.sync_payment_status()
		self.assertEqual(self.rows(so_name), expected)

	# --- desk orders bill each attendee at their own price (phamos/phamos#1711) -------------------------------

	def desk_order(self, event, attendees):
		customer = make_customer("Desk Price Kunde AG")
		so = frappe.get_doc("Sales Order", create_sales_orders([a.name for a in attendees], customer=customer)["sales_orders"][0])
		return {row.name: row.rate for row in so.items}, so

	def early_bird_event(self, **row):
		return make_event("Desk Price Event", prices=[{"title": "Early Bird", "rate": 59.5, "quota": 2, **row},
			{"title": "Regular", "rate": 119}])

	def test_desk_order_keeps_the_early_bird_price_the_attendees_filled(self, enqueue):
		event = self.early_bird_event()
		people = [make_attendee(event.name, f"early{i}@desk.example", ticket_type="Early Bird") for i in range(2)]
		rates, so = self.desk_order(event, people)
		self.assertEqual(set(rates.values()), {59.5})  # before: the quota counted them, so Regular
		self.assertEqual(set(frappe.get_all("Attendee", filters={"sales_order": so.name}, pluck="ticket_type")), {"Early Bird"})

	def test_desk_order_after_the_sale_window(self, enqueue):
		event = self.early_bird_event(valid_until=frappe.utils.add_days(frappe.utils.now_datetime(), -1))
		person = make_attendee(event.name, "late@desk.example", ticket_type="Early Bird")
		rates, _so = self.desk_order(event, [person])
		self.assertEqual(list(rates.values()), [59.5])

	def test_unknown_ticket_type_gets_the_current_price(self, enqueue):
		event = self.early_bird_event()
		# One order (same order reference), so both land on one Sales Order.
		known = make_attendee(event.name, "known@desk.example", ticket_type="Regular", order_reference="DESK-1")
		unknown = make_attendee(event.name, "unknown@desk.example", ticket_type="Old Name", order_reference="DESK-1")
		_rates, so = self.desk_order(event, [known, unknown])
		self.assertEqual(sorted(row.rate for row in so.items), [59.5, 119])  # one order, two rates
		self.assertEqual(frappe.db.get_value("Attendee", unknown.name, "ticket_type"), "Early Bird")
		self.assertEqual(frappe.db.get_value("Attendee", known.name, "ticket_type"), "Regular")

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


class TestSalesOrderHookCost(FrappeTestCase):
	"""phamos/phamos#1707: the hook runs on every Sales Order save, also for orders without attendees."""

	def test_order_without_attendees_costs_one_query(self):
		order = SimpleNamespace(name="SO-NOT-AN-EVENT", customer="Someone", docstatus=0,
			items=[SimpleNamespace(name=f"line-{i}") for i in range(50)])
		with self.assertQueryCount(1):
			billing.on_sales_order_update(order)

	def test_attendee_links_are_indexed(self):
		meta = frappe.get_meta("Attendee")
		for field in ("event", "sales_order", "sales_order_item", "sales_invoice"):
			self.assertTrue(meta.get_field(field).search_index, field)
