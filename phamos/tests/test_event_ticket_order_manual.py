"""Event Ticket Orders created by hand in the desk (phamos/phamos#1730).

bench --site <site> run-tests --module phamos.tests.test_event_ticket_order_manual
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from phamos.marketing import api, ticketing
from phamos.tests.marketing_fixtures import BILLING, as_guest, ensure_company, make_attendee, make_customer, make_event


@patch("frappe.enqueue")
class TestManualEventTicketOrder(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_company()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("manual_ticket_order_test")
		self.event = make_event("Manual Ticket Order Event", prices=[{"title": "Early Bird", "rate": 59.5},
			{"title": "Regular", "rate": 119}])

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.after_commit.reset()
		frappe.db.rollback(save_point="manual_ticket_order_test")

	def desk_order(self, event=None, **values):
		return frappe.get_doc({"doctype": "Event Ticket Order", "event": (event or self.event).name,
			"buyer_first_name": "Doris", "buyer_last_name": "Desk", "buyer_email": "doris@manual-order.example",
			"ticket_type": "Regular", **values}).insert()

	def add_ticket(self, order, email):
		return make_attendee(order.event, email, event_ticket_order=order.name, ticket_type=order.ticket_type)

	def test_desk_order_takes_the_price_and_follows_its_tickets(self, enqueue):
		order = self.desk_order()
		self.assertEqual((order.source, order.status, order.ticket_rate, order.ticket_rate_includes_tax),
			("Desk", "Booked", 119, 1))
		self.assertEqual(order.item_tax_template, self.event.item_tax_template)
		self.assertTrue(order.ordered_on)
		# "Buyer attends" (default): the buyer's own ticket, created with the order.
		buyer = frappe.get_all("Attendee", filters={"event_ticket_order": order.name},
			fields=["is_buyer", "first_name", "email", "ticket_type", "payment_status"])
		self.assertEqual([(b.is_buyer, b.first_name, b.email, b.ticket_type, b.payment_status) for b in buyer],
			[(1, "Doris", "doris@manual-order.example", "Regular", "Pending")])
		self.assertEqual((order.quantity, flt(order.confirmed_total)), (1, 119))

		mate = self.add_ticket(order, "mate@manual-order.example")
		order.reload()
		self.assertEqual((order.quantity, flt(order.confirmed_total)), (2, 238))
		mate.status = "Cancelled"
		mate.save()
		order.reload()
		self.assertEqual((order.quantity, flt(order.confirmed_total), order.status), (1, 119, "Booked"))

	def test_typed_rate_is_kept(self, enqueue):
		order = self.desk_order(ticket_rate=100, buyer_attends=0)
		self.assertEqual((order.ticket_rate, order.quantity, order.confirmed_total), (100, 0, 0))
		self.add_ticket(order, "special@manual-order.example")
		order.reload()
		self.assertEqual((order.quantity, flt(order.confirmed_total)), (1, 100))

	def test_price_must_be_one_of_the_event(self, enqueue):
		self.assertRaises(frappe.ValidationError, self.desk_order, ticket_type="Gold")
		self.assertRaises(frappe.ValidationError, self.desk_order, ticket_type="")

	def test_free_event(self, enqueue):
		event = make_event("Manual Free Ticket Order Event", paid=False)
		order = self.desk_order(event=event, ticket_type=None)
		self.assertEqual((order.status, order.ticket_type, order.quantity, order.confirmed_total), ("Free", "Free", 1, 0))
		self.assertEqual(frappe.db.get_value("Attendee", {"event_ticket_order": order.name}, "payment_status"),
			"Not Required")

	def test_event_cannot_change_once_tickets_exist(self, enqueue):
		other = make_event("Manual Ticket Order Other Event")
		order = self.desk_order()
		order.event = other.name
		self.assertRaises(frappe.ValidationError, order.save)
		empty = self.desk_order(buyer_attends=0)
		empty.event = other.name
		empty.save()

	def test_sales_order_at_the_desk_price_then_locked(self, enqueue):
		customer = make_customer("Manual Order Customer GmbH")
		order = self.desk_order(ticket_type="Early Bird", customer=customer)
		self.add_ticket(order, "colleague@manual-order.example")
		order.reload()
		self.assertEqual(api.order_customer_proposal(order.name).action, "use")
		so_name = api.create_order_sales_orders([order.name], mode="use", customer=customer)["sales_orders"][0]
		so = frappe.get_doc("Sales Order", so_name)
		self.assertEqual((so.customer, flt(so.grand_total, 2), so.event_ticket_order), (customer, 119.0, order.name))
		order.reload()
		self.assertEqual(order.status, "Ordered")
		order.buyer_phone = "+49 7121 0"
		self.assertRaises(frappe.ValidationError, order.save)

	def test_website_order_stays_read_only(self, enqueue):
		with as_guest():
			result = ticketing.register_attendees(self.event.name, {"full_name": "Wanda Web", "email": "wanda@manual-order.example"},
				billing_data={**BILLING, "full_name": "Wanda Web", "email": "wanda@manual-order.example"})
		order = frappe.get_doc("Event Ticket Order", result["reference"])
		self.assertEqual(order.source, "Website")
		order.ticket_rate = 1
		self.assertRaises(frappe.ValidationError, order.save)
