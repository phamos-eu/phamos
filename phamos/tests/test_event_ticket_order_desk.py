"""Desk "Create Sales Order" on the Event Ticket Order: Customer choice, stored price, total check (phamos/phamos#1725).

bench --site <site> run-tests --module phamos.tests.test_event_ticket_order_desk
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from phamos.marketing import api, ticketing
from phamos.tests.marketing_fixtures import BILLING, as_guest, ensure_company, make_customer, make_event

CLERK = "ticket-order-clerk@ticket.example"


@patch("frappe.enqueue")
class TestEventTicketOrderDesk(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_company()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("ticket_order_desk_test")
		self.event = make_event("Ticket Order Desk Event")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.after_commit.reset()
		frappe.db.rollback(save_point="ticket_order_desk_test")
		frappe.clear_cache(user=CLERK)

	def order(self, email="buyer@order-desk.example", company=None, event=None, **billing):
		"""A paid website order: the buyer and one companion, 2 × 119 € incl. VAT."""
		data = {**BILLING, "full_name": "Olga Order", "email": email, **billing}
		if company:
			data.update(is_company=1, company=company)
		with as_guest():
			result = ticketing.register_attendees((event or self.event).name, {"full_name": "Olga Order", "email": email},
				companions=[{"full_name": "Carl Companion", "email": f"companion.{email}"}], billing_data=data)
		return frappe.get_doc("Event Ticket Order", result["reference"])

	def tickets(self, order):
		return frappe.get_all("Attendee", filters={"event_ticket_order": order.name},
			fields=["name", "payment_status", "billing_customer", "is_buyer", "customer"])

	def customer_addresses(self, customer):
		return frappe.get_all("Dynamic Link", filters={"parenttype": "Address", "link_doctype": "Customer",
			"link_name": customer}, pluck="parent")

	def test_lead_buyer_is_converted(self, enqueue):
		order = self.order(company="Olga Order Werkstatt GmbH", vat_id="DE123456789")
		self.assertTrue(order.lead)
		proposal = api.order_customer_proposal(order.name)
		self.assertEqual((proposal.action, proposal.unambiguous), ("convert", True))

		so_name = api.create_order_sales_orders([order.name], mode="convert", submit=1)["sales_orders"][0]
		customer = frappe.db.get_value("Customer", {"lead_name": order.lead},
			["name", "customer_name", "customer_type", "tax_id"], as_dict=True)
		self.assertEqual((customer.customer_name, customer.customer_type, customer.tax_id),
			("Olga Order Werkstatt GmbH", "Company", "DE123456789"))
		self.assertEqual(frappe.db.get_value("Lead", order.lead, "status"), "Converted")
		self.assertTrue(frappe.db.exists("Dynamic Link", {"parenttype": "Contact", "parent": order.contact,
			"link_doctype": "Customer", "link_name": customer.name}))
		self.assertEqual(len(self.customer_addresses(customer.name)), 1)

		so = frappe.get_doc("Sales Order", so_name)
		self.assertEqual((so.docstatus, so.customer, flt(so.grand_total, 2)), (1, customer.name, 238.0))
		self.assertEqual((so.contact_person, so.customer_address), (order.contact, self.customer_addresses(customer.name)[0]))
		order.reload()
		self.assertEqual((order.status, order.customer), ("Ordered", customer.name))
		# The Sales Order points to the order, each line to its ticket (phamos/phamos#1727).
		self.assertEqual(so.event_ticket_order, order.name)
		tickets = self.tickets(order)
		self.assertEqual(sorted(row.attendee for row in so.items), sorted(t.name for t in tickets))
		for ticket in tickets:
			self.assertEqual((ticket.payment_status, ticket.billing_customer), ("Ordered", customer.name))
		buyer = next(t for t in self.tickets(order) if t.is_buyer)
		self.assertEqual(buyer.customer, customer.name)

	def test_customer_buyer_uses_it_and_gets_the_billing_address_once(self, enqueue):
		customer = make_customer("Order Desk Kunde AG", email="known@order-desk.example")
		first = self.order(email="known@order-desk.example")
		self.assertEqual((first.customer, first.lead), (customer, None))
		proposal = api.order_customer_proposal(first.name)
		self.assertEqual((proposal.action, proposal.customer, proposal.unambiguous), ("use", customer, True))
		api.create_order_sales_orders([first.name], mode="use", customer=customer, submit=1)
		self.assertEqual(len(self.customer_addresses(customer)), 1)
		self.assertEqual(frappe.db.get_value("Customer", customer, "tax_id"), None)

		second = self.order(email="known@order-desk.example", event=make_event("Ticket Order Desk Second Event"),
			address_line1="hauptstr.  1")  # the same address, typed differently
		api.create_order_sales_orders([second.name], mode="use", customer=customer, submit=1)
		self.assertEqual(len(self.customer_addresses(customer)), 1)

	def test_vat_id_is_never_overwritten(self, enqueue):
		customer = make_customer("Order Desk VAT AG", email="vat@order-desk.example")
		frappe.db.set_value("Customer", customer, "tax_id", "DE111111111")
		order = self.order(email="vat@order-desk.example", company="Order Desk VAT AG", vat_id="DE999999999")
		api.create_order_sales_orders([order.name], mode="use", customer=customer, submit=1)
		self.assertEqual(frappe.db.get_value("Customer", customer, "tax_id"), "DE111111111")
		self.assertTrue(frappe.db.exists("Comment", {"reference_doctype": "Customer", "reference_name": customer,
			"content": ["like", "%DE999999999%"]}))

	def test_lead_buyer_linked_to_another_customer(self, enqueue):
		order = self.order(email="lead.other@order-desk.example")
		other = make_customer("Order Desk Andere GmbH")
		api.create_order_sales_orders([order.name], mode="use", customer=other, submit=1)
		self.assertEqual(frappe.db.get_value("Lead", order.lead, ["customer", "status"]), (other, "Converted"))
		self.assertFalse(frappe.db.exists("Customer", {"lead_name": order.lead}))
		self.assertEqual(frappe.db.get_value("Event Ticket Order", order.name, "customer"), other)

	def test_new_customer_from_the_billing_data(self, enqueue):
		make_customer("Order Desk Alt AG", email="new.customer@order-desk.example")
		order = self.order(email="new.customer@order-desk.example", company="Order Desk Neu AG")
		so = frappe.get_doc("Sales Order", api.create_order_sales_orders([order.name], mode="new", submit=1)["sales_orders"][0])
		self.assertEqual(frappe.db.get_value("Customer", so.customer, ["customer_name", "customer_type"]),
			("Order Desk Neu AG", "Company"))

	def test_stored_rate_after_a_price_change(self, enqueue):
		order = self.order()
		self.event.reload()
		self.event.ticket_prices[0].rate = 200
		self.event.save()
		so = frappe.get_doc("Sales Order", api.create_order_sales_orders([order.name], mode="convert", submit=1)["sales_orders"][0])
		self.assertEqual([flt(row.rate, 2) for row in so.items], [119.0, 119.0])
		self.assertEqual(flt(so.grand_total, 2), 238.0)

	def test_cancelled_ticket_is_not_ordered(self, enqueue):
		order = self.order()
		companion = next(t for t in self.tickets(order) if not t.is_buyer)
		frappe.db.set_value("Attendee", companion.name, "status", "Cancelled")
		so = frappe.get_doc("Sales Order", api.create_order_sales_orders([order.name], mode="convert", submit=1)["sales_orders"][0])
		self.assertEqual((len(so.items), flt(so.grand_total, 2)), (1, 119.0))

	def test_total_mismatch_is_refused(self, enqueue):
		order = self.order()
		frappe.db.set_value("Event Ticket Order", order.name, "confirmed_total", 1)
		with patch("frappe.log_error") as log_error, self.assertRaises(frappe.ValidationError) as raised:
			api.create_order_sales_orders([order.name], mode="convert", submit=1)
		self.assertIn("Total differs from the confirmed total", str(raised.exception))
		log_error.assert_called_once()

	def test_draft_sales_order_is_not_checked(self, enqueue):
		# phamos/phamos#1730: the desk gets a draft to check and change by hand, whatever its total.
		order = self.order()
		frappe.db.set_value("Event Ticket Order", order.name, "confirmed_total", 1)
		so = frappe.get_doc("Sales Order", api.create_order_sales_orders([order.name], mode="convert")["sales_orders"][0])
		self.assertEqual((so.docstatus, flt(so.grand_total, 2), so.event_ticket_order), (0, 238.0, order.name))
		self.assertEqual(frappe.db.get_value("Event Ticket Order", order.name, "status"), "Booked")
		# The form opens this draft; the list action skips the order.
		self.assertEqual(api.order_customer_proposal(order.name).sales_order, so.name)
		result = api.create_order_sales_orders([order.name])
		self.assertEqual((result["sales_orders"], [row["order"] for row in result["skipped"]]), ([], [order.name]))
		so.submit()
		self.assertEqual(frappe.db.get_value("Event Ticket Order", order.name, "status"), "Ordered")

	def test_user_without_sales_order_rights(self, enqueue):
		order = self.order()
		role = "Ticket Order Clerk"
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
		frappe.get_doc({"doctype": "Custom DocPerm", "parent": "Event Ticket Order", "parenttype": "DocType",
			"parentfield": "permissions", "role": role, "read": 1, "write": 1}).insert(ignore_permissions=True)
		frappe.get_doc({"doctype": "Custom DocPerm", "parent": "Attendee", "parenttype": "DocType",
			"parentfield": "permissions", "role": role, "read": 1, "write": 1}).insert(ignore_permissions=True)
		if not frappe.db.exists("User", CLERK):
			frappe.get_doc({"doctype": "User", "email": CLERK, "first_name": "Clerk", "send_welcome_email": 0,
				"roles": [{"role": role}]}).insert(ignore_permissions=True)
		frappe.clear_cache(doctype="Event Ticket Order")
		frappe.clear_cache(doctype="Attendee")
		frappe.set_user(CLERK)
		self.assertTrue(frappe.has_permission("Event Ticket Order", "write", order.name))
		self.assertRaises(frappe.PermissionError, api.create_order_sales_orders, [order.name], mode="convert", submit=1)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Lead", order.lead, "status"), "Lead")
		frappe.clear_cache(doctype="Event Ticket Order")
		frappe.clear_cache(doctype="Attendee")

	def test_bulk_skips_ambiguous_and_unbooked_orders(self, enqueue):
		clear = self.order(email="clear@order-desk.example")
		make_customer("Order Desk Bekannt GmbH")
		similar = self.order(email="similar@order-desk.example", company="Order Desk Bekannt GmbH")
		free_event = make_event("Ticket Order Desk Free Event", paid=False)
		with as_guest():
			free = ticketing.register_attendees(free_event.name, {"full_name": "Fred Free", "email": "free@order-desk.example"})
		result = api.create_order_sales_orders([clear.name, similar.name, free["reference"]], submit=1)
		self.assertEqual(len(result["sales_orders"]), 1)
		self.assertEqual(frappe.db.get_value("Event Ticket Order", clear.name, "status"), "Ordered")
		self.assertEqual({row["order"]: row["reason"] for row in result["skipped"]},
			{similar.name: "choose the Customer in the order", free["reference"]: "not booked (Free)"})
		self.assertRaises(frappe.ValidationError, api.create_order_sales_orders, [clear.name, similar.name], mode="new", submit=1)

	def test_invoice_from_the_order(self, enqueue):
		order = self.order()
		api.create_order_sales_orders([order.name], mode="convert", submit=1)
		invoices = api.create_sales_invoices(ticket_orders=[order.name], submit=1)["sales_invoices"]
		self.assertEqual(len(invoices), 1)
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", invoices[0], "grand_total"), 2), 238.0)
		self.assertEqual(frappe.db.get_value("Event Ticket Order", order.name, "status"), "Invoiced")
		# ERPNext's mapper copies both links to the invoice and to a credit note (phamos/phamos#1727).
		si = frappe.get_doc("Sales Invoice", invoices[0])
		names = sorted(t.name for t in self.tickets(order))
		self.assertEqual((si.event_ticket_order, sorted(row.attendee for row in si.items)), (order.name, names))
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		credit_note = make_sales_return(si.name)
		credit_note.insert()
		credit_note.submit()
		self.assertEqual((credit_note.event_ticket_order, sorted(row.attendee for row in credit_note.items)),
			(order.name, names))
		self.assertEqual(frappe.db.get_value("Event Ticket Order", order.name, "status"), "Credited")

	def test_connections_list_every_sales_document(self, enqueue):
		from frappe.desk.notifications import get_open_count

		order = self.order()
		so_name = api.create_order_sales_orders([order.name], mode="convert", submit=1)["sales_orders"][0]
		api.create_sales_invoices(ticket_orders=[order.name], submit=1)
		def counts(doctype, name):
			found = get_open_count(doctype, name)["count"]["external_links_found"]
			return {d["doctype"]: d["count"] for d in found}

		self.assertEqual(counts("Event Ticket Order", order.name), {"Attendee": 2, "Sales Order": 1, "Sales Invoice": 1})
		buyer = next(t for t in self.tickets(order) if t.is_buyer)
		# Through the line field: Frappe resolves "attendee" on the items table, as ERPNext's Item does.
		self.assertEqual(counts("Attendee", buyer.name), {"Sales Order": 1, "Sales Invoice": 1})
		self.assertEqual(frappe.db.get_value("Sales Order", so_name, "event_ticket_order"), order.name)

	def test_a_ticket_is_on_one_sales_order_only(self, enqueue):
		order = self.order()
		so = frappe.get_doc("Sales Order", api.create_order_sales_orders([order.name], mode="convert", submit=1)["sales_orders"][0])
		duplicate = frappe.copy_doc(so)
		self.assertRaisesRegex(frappe.ValidationError, "is already on Sales Order", duplicate.insert)
		so.cancel()
		self.assertEqual(frappe.db.get_value("Event Ticket Order", order.name, "status"), "Booked")
		duplicate.insert()  # once the first one is cancelled the tickets can be ordered again
