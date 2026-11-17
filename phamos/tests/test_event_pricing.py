"""Event pricing: the page total is the Sales Order total, and no ticket sale without an Item Tax Template
(phamos/phamos#1710).

bench --site <site> run-tests --module phamos.tests.test_event_pricing
"""

import io
from contextlib import redirect_stdout
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from phamos.marketing import billing, ticketing
from phamos.patches.v1_0 import report_paid_events_without_tax_template
from phamos.tests.marketing_fixtures import BILLING, CONTACT, as_guest, ensure_company, make_customer, make_event

TWO_COMPANIONS = [{"full_name": "Max Mustermann", "email": ""}, {"full_name": "Moritz Mustermann", "email": ""}]


@patch("frappe.enqueue")
class TestEventPricing(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_company()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("event_pricing_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in frappe.get_all("Marketing Content", pluck="name"):
			frappe.cache.delete_value(ticketing._holds_key(name))
		frappe.db.after_commit.reset()
		frappe.db.rollback(save_point="event_pricing_test")

	def order(self, event, **kwargs):
		with as_guest():
			return ticketing.register_attendees(event.name, CONTACT, attends=1, companions=TWO_COMPANIONS,
				billing_data=BILLING, **kwargs)

	def desk_order(self, event, ticket_order, confirmed_total):
		"""The Sales Order the desk creates for a website order (phamos/phamos#1725), at the attendees' own price."""
		attendees = [frappe.get_doc("Attendee", name) for name in
			frappe.get_all("Attendee", filters={"event_ticket_order": ticket_order}, pluck="name", order_by="creation asc")]
		return billing.create_sales_order(event, attendees, make_customer("Desk Pricing Kunde AG"), submit=True,
			confirmed_total=confirmed_total)

	# --- 1. one total --------------------------------------------------------------------------------

	def test_net_prices_page_total_is_the_sales_order_total(self, enqueue):
		event = make_event("Net Price Event", ticket_price_includes_tax=0, prices=[{"title": "Regular", "rate": 10.01}])
		pricing = billing.get_ticket_pricing(event, 3)
		# Tax once on the order's net total, as ERPNext does: 30.03 + 5.71 = 35.74 (not 3 × 11.91 = 35.73).
		self.assertEqual(billing.order_total(pricing, 3), {"net_total": 30.03, "tax_total": 5.71, "total": 35.74})
		self.assertEqual(ticketing.hold_seats(event, "hold-net-price-1", 3)["total"], 35.74)
		result = self.order(event, expected_total=35.74)
		self.assertEqual(frappe.db.get_value("Event Ticket Order", result["reference"], "confirmed_total"), 35.74)
		so = self.desk_order(event, result["reference"], 35.74)
		self.assertEqual(flt(so.grand_total, 2), 35.74)
		self.assertTrue(so.disable_rounded_total)

	def test_gross_prices_total_is_qty_times_gross(self, enqueue):
		event = make_event("Gross Price Event")
		pricing = billing.get_ticket_pricing(event, 3)
		self.assertEqual(billing.order_total(pricing, 3).total, 357.0)
		result = self.order(event, expected_total=357)
		self.assertEqual(flt(self.desk_order(event, result["reference"], 357).grand_total, 2), 357.0)

	def test_order_is_refused_when_erpnext_computes_another_total(self, enqueue):
		# Since phamos/phamos#1724 the Sales Order is created in the desk; the check still guards it there.
		event = make_event("Mismatch Event")
		result = self.order(event)
		with patch("frappe.log_error") as log_error, self.assertRaises(frappe.ValidationError):
			self.desk_order(event, result["reference"], 1.0)
		log_error.assert_called_once()
		self.assertTrue(log_error.call_args.kwargs["defer_insert"])  # survives the rollback of the request

	# --- 2. no ticket sale without an Item Tax Template ------------------------------------------------

	def test_open_paid_event_needs_an_item_tax_template(self, enqueue):
		name = make_event("Template Event").name
		event = frappe.get_doc("Marketing Content", name)
		event.item_tax_template = None
		self.assertRaises(frappe.ValidationError, event.save)
		event = frappe.get_doc("Marketing Content", name)
		event.item_tax_template = None
		event.registration_open = 0
		event.save()  # a closed or draft event may be saved without one

	def test_tax_templates_must_belong_to_the_company(self, enqueue):
		event = make_event("Company Event")
		with patch.object(billing, "default_company", return_value="Some Other Company"):
			self.assertRaises(frappe.ValidationError, event.save)

	def test_sale_is_closed_without_an_item_tax_template(self, enqueue):
		event = make_event("Closed Template Event")
		frappe.db.set_value("Marketing Content", event.name, "item_tax_template", None)
		event.reload()
		self.assertEqual(ticketing.sale_state(event), (False, "no_tax_template"))
		self.assertEqual(ticketing.hold_seats(event, "hold-no-template-1", 1), {"ok": False, "reason": "no_tax_template"})
		offer = ticketing.offer(event.name)  # the page renders, without any price
		self.assertEqual((offer.sale_open, offer.reason, offer.gross, offer.prices), (False, "no_tax_template", 0, []))
		with self.assertRaises(frappe.ValidationError) as raised:
			billing.get_ticket_pricing(event)  # also stops desk orders for this event
		self.assertIn("Closed Template Event", str(raised.exception))

	def test_tax_rate_comes_from_the_item_tax_template(self, enqueue):
		company = billing.default_company()
		low, high = frappe.get_all("Account", filters={"company": company, "account_type": "Tax", "is_group": 0},
			pluck="name", order_by="name", limit=2)
		sales = frappe.get_doc({"doctype": "Sales Taxes and Charges Template", "title": "Test 7 and 19",
			"company": company, "taxes": [
				{"charge_type": "On Net Total", "account_head": low, "rate": 7, "description": "VAT 7"},
				{"charge_type": "On Net Total", "account_head": high, "rate": 19, "description": "VAT 19"}]}).insert()
		item = frappe.get_doc({"doctype": "Item Tax Template", "title": "Test Only 19", "company": company,
			"taxes": [{"tax_type": low, "not_applicable": 1}, {"tax_type": high, "tax_rate": 19}]}).insert()
		event = frappe._dict(taxes_and_charges=sales.name, item_tax_template=item.name)
		self.assertEqual(sum(row.tax_rate for row in billing.tax_rows(event)), 19)  # not 7 + 19 = 26
		self.assertEqual(billing.tax_rows(frappe._dict(taxes_and_charges=sales.name)), [])

	def test_patch_lists_paid_events_without_a_template(self, enqueue):
		event = make_event("Report Template Event")
		frappe.db.set_value("Marketing Content", event.name, "item_tax_template", None)
		with redirect_stdout(io.StringIO()) as out:
			report_paid_events_without_tax_template.execute()
		self.assertIn("Report Template Event", out.getvalue())
		self.assertFalse(frappe.db.get_value("Marketing Content", event.name, "item_tax_template"))  # unchanged
