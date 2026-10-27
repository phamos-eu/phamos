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


def tickets_of(so_name):
	"""The Attendees on a Sales Order's lines (phamos/phamos#1727: the lines point to them)."""
	return frappe.get_all("Sales Order Item", filters={"parent": so_name, "attendee": ["is", "set"]}, pluck="attendee")


def order_statuses(so_name):
	return statuses(name=["in", tickets_of(so_name)])


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
		"""A website order and the Sales Order the desk creates for it (since phamos/phamos#1724 the website
		creates none). Returns the Sales Order."""
		with as_guest():
			result = ticketing.register_attendees(self.event.name, {"full_name": "Bill Buyer", "email": "bill@billing.example"},
				companions=[{"full_name": "Colleague One", "email": "colleague@billing.example"}],
				billing_data={**BILLING, "full_name": "Bill Buyer", "email": "bill@billing.example",
					"is_company": 1, "company": "Billing Test GmbH"})
		names = frappe.get_all("Attendee", filters={"event_ticket_order": result["reference"]}, pluck="name")
		return create_sales_orders(names, customer=make_customer("Billing Test GmbH"), submit=1)["sales_orders"][0]

	def test_invoice_payment_and_cancel(self, enqueue):
		so_name = self.web_order()
		self.assertEqual(order_statuses(so_name), {"Ordered"})
		# The Sales Order leaves the legacy order reference empty (phamos/phamos#1729).
		self.assertFalse(any(frappe.get_all("Attendee", filters={"name": ["in", tickets_of(so_name)]}, pluck="order_reference")))
		invoices = create_sales_invoices(names=tickets_of(so_name), submit=1)["sales_invoices"]
		self.assertEqual(len(invoices), 1)
		si = frappe.get_doc("Sales Invoice", invoices[0])
		self.assertEqual(si.grand_total, 238)
		self.assertEqual(order_statuses(so_name), {"Invoiced"})
		self.assertEqual({invoice for invoice, _status in billing.payment_state(tickets_of(so_name)).values()}, {si.name})

		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		pe = get_payment_entry("Sales Invoice", si.name)
		pe.reference_no, pe.reference_date = "TEST", frappe.utils.nowdate()
		pe.insert()
		pe.submit()
		self.assertEqual(order_statuses(so_name), {"Paid"})
		pe.cancel()
		self.assertEqual(order_statuses(so_name), {"Invoiced"})
		si.reload()
		si.cancel()
		self.assertEqual(order_statuses(so_name), {"Ordered"})
		frappe.get_doc("Sales Order", so_name).cancel()
		self.assertEqual(order_statuses(so_name), {"Pending"})

	# --- credit notes (phamos/phamos#1706) ------------------------------------------------------------

	def invoice(self, so_name):
		return frappe.get_doc("Sales Invoice", create_sales_invoices(names=tickets_of(so_name), submit=1)["sales_invoices"][0])

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
		"""{attendee: (current invoice, stored payment_status)} of a Sales Order's tickets."""
		names = tickets_of(so_name)
		invoices = billing.payment_state(names)
		return {r.name: (invoices.get(r.name, (None, None))[0], r.payment_status) for r in frappe.get_all("Attendee",
			filters={"name": ["in", names]}, fields=["name", "payment_status"])}

	def test_partial_credit_note_on_a_paid_invoice(self, enqueue):
		so_name = self.web_order()
		si = self.invoice(so_name)
		self.pay(si)
		cn = self.credit_note(si, lines=1)
		credited_line = cn.items[0].attendee  # copied from the invoice by ERPNext's mapper
		for line, (invoice, status) in self.rows(so_name).items():
			self.assertEqual(invoice, si.name)  # never the credit note
			self.assertEqual(status, "Credited" if line == credited_line else "Paid")

	def test_full_credit_then_a_new_invoice(self, enqueue):
		so_name = self.web_order()
		si = self.invoice(so_name)
		# Without "Update Billed Amount in Sales Order" the order stays fully billed and ERPNext refuses the new invoice.
		cn = self.credit_note(si, submit=False)
		cn.update_billed_amount_in_sales_order = 1
		cn.save()
		cn.submit()
		self.assertEqual(set(self.rows(so_name).values()), {(si.name, "Credited")})
		# The usual correction: a credit note, then a new invoice for the same order lines (a copy of the original).
		corrected = frappe.copy_doc(si)
		corrected.docstatus = 0  # copy_doc keeps it during tests
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
		si = frappe.get_doc("Sales Invoice", create_sales_invoices(names=tickets_of(so_name), submit=0)["sales_invoices"][0])
		with patch.object(billing, "on_sales_invoice_change", wraps=billing.on_sales_invoice_change) as hook:
			si.submit()
		self.assertEqual(hook.call_count, 2)
		self.assertEqual(set(self.rows(so_name).values()), {(si.name, "Invoiced")})

	def test_daily_sync_matches_the_hooks(self, enqueue):
		so_name = self.web_order()
		si = self.invoice(so_name)
		self.pay(si)
		expected = self.rows(so_name)
		for name in tickets_of(so_name):
			frappe.db.set_value("Attendee", name, "payment_status", "Invoiced")
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
		self.assertEqual(set(frappe.get_all("Attendee", filters={"name": ["in", tickets_of(so.name)]}, pluck="ticket_type")), {"Early Bird"})

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
		names = frappe.get_all("Attendee", filters={"name": ["in", tickets_of(so_name)]}, pluck="name", order_by="creation asc")
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
		self.assertEqual(order_statuses(so.name), {"Ordered"})
		self.assertEqual(set(frappe.get_all("Attendee", filters={"name": ["in", tickets_of(so.name)]}, pluck="order_reference")), {"SHEET-1"})

	def test_price_summary(self, enqueue):
		self.assertIn("Regular", billing.price_summary(self.event))
		self.assertIn("119", self.event.ticket_price_summary)


class TestSalesOrderHookCost(FrappeTestCase):
	"""phamos/phamos#1707: the hook runs on every Sales Order save, also for orders without attendees."""

	def test_order_without_attendees_costs_no_query(self):
		# Since phamos/phamos#1727 the lines name their tickets: an order without any needs no query at all.
		order = SimpleNamespace(name="SO-NOT-AN-EVENT", customer="Someone", docstatus=0,
			items=[SimpleNamespace(name=f"line-{i}") for i in range(50)])
		with self.assertQueryCount(0):
			billing.on_sales_order_update(order)

	def test_ticket_links_are_indexed(self):
		self.assertTrue(frappe.get_meta("Attendee").get_field("event").search_index)
		for doctype, field in (("Sales Order", "event_ticket_order"), ("Sales Invoice", "event_ticket_order"),
				("Sales Order Item", "attendee"), ("Sales Invoice Item", "attendee")):
			self.assertTrue(frappe.get_meta(doctype).get_field(field).search_index, f"{doctype}.{field}")
