"""Event Ticket Order: one order with its tickets, status computed from them (phamos/phamos#1723).

bench --site <site> run-tests --module phamos.tests.test_event_ticket_order
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.marketing import billing
from phamos.marketing.doctype.event_ticket_order.event_ticket_order import order_status, refresh_status
from phamos.tests.marketing_fixtures import ensure_company, make_attendee, make_event


def ticket(payment_status, status="Registered"):
	return frappe._dict(payment_status=payment_status, status=status)


@patch("frappe.enqueue")
class TestEventTicketOrder(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_company()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("ticket_order_test")
		self.event = make_event("Ticket Order Event", paid=False)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="ticket_order_test")

	def make_order(self, **values):
		return frappe.get_doc({"doctype": "Event Ticket Order", "event": self.event.name,
			"source": "Website", "buyer_first_name": "Erika", "buyer_last_name": "Muster", "buyer_email": "erika@order.example",
			"quantity": 2, **values}).insert(ignore_permissions=True)

	def test_naming_series_and_buyer_name(self, enqueue):
		order = self.make_order()
		self.assertRegex(order.name, r"^TO-\d{4}-\d{5}$")
		self.assertEqual(order.buyer_name, "Erika Muster")

	def test_status_table(self, enqueue):
		cases = [
			([], "Booked"),
			([ticket("Not Required"), ticket("Not Required")], "Free"),
			([ticket("Pending"), ticket("Pending")], "Booked"),
			([ticket("Ordered"), ticket("Pending")], "Ordered"),
			([ticket("Invoiced"), ticket("Ordered")], "Invoiced"),
			([ticket("Paid"), ticket("Ordered")], "Invoiced"),
			([ticket("Paid"), ticket("Paid")], "Paid"),
			([ticket("Paid"), ticket("Paid"), ticket("Credited")], "Paid"),
			([ticket("Credited"), ticket("Credited")], "Credited"),
			([ticket("Paid"), ticket("Pending", status="Cancelled")], "Paid"),
			([ticket("Pending", status="Cancelled"), ticket("Paid", status="Cancelled")], "Cancelled"),
		]
		for tickets, expected in cases:
			self.assertEqual(order_status(tickets), expected, [t.payment_status for t in tickets])

	def test_attendee_update_refreshes_the_order(self, enqueue):
		order = self.make_order()
		a = make_attendee(self.event.name, "one@order.example", event_ticket_order=order.name, payment_status="Pending")
		make_attendee(self.event.name, "two@order.example", event_ticket_order=order.name, payment_status="Pending")
		self.assertEqual(frappe.db.get_value("Event Ticket Order", order.name, "status"), "Booked")
		a.reload()
		a.status = "Cancelled"
		a.save()
		self.assertEqual(frappe.db.get_value("Event Ticket Order", order.name, "status"), "Booked")
		frappe.db.set_value("Attendee", {"event_ticket_order": order.name}, "payment_status", "Not Required")
		refresh_status(order.name)
		self.assertEqual(frappe.db.get_value("Event Ticket Order", order.name, "status"), "Free")

	def test_billing_writes_refresh_the_order_and_its_customer(self, enqueue):
		order = self.make_order()
		names = [make_attendee(self.event.name, f"t{i}@order.example", event_ticket_order=order.name,
			payment_status="Pending").name for i in range(2)]
		for name in names:
			frappe.db.set_value("Attendee", name, {"payment_status": "Ordered",
				"billing_customer": "Test Ticket Order Customer"})
		billing._refresh_orders(names)
		self.assertEqual(frappe.db.get_value("Event Ticket Order", order.name, ["status", "customer"]),
			("Ordered", "Test Ticket Order Customer"))

	def test_event_connections_list_its_orders_and_tickets(self, enqueue):
		# phamos/phamos#1728: the event's Connections tab shows its Event Ticket Orders next to the Attendees.
		from frappe.desk.notifications import get_open_count

		order = self.make_order()
		make_attendee(self.event.name, "t@connections.example", event_ticket_order=order.name)
		found = get_open_count("Marketing Content", self.event.name)["count"]["external_links_found"]
		counts = {d["doctype"]: d["count"] for d in found}
		self.assertEqual((counts.get("Event Ticket Order"), counts.get("Attendee")), (1, 1))

	def test_guests_cannot_read_orders(self, enqueue):
		order = self.make_order()
		frappe.set_user("Guest")
		self.assertFalse(frappe.has_permission("Event Ticket Order", "read", order.name))
