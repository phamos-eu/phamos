"""Website orders: validation, CRM records, Attendees and the Quotation, all as Guest.

bench --site <site> run-tests --module phamos.tests.test_marketing_ticketing
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from phamos.marketing import ticketing
from phamos.tests.marketing_fixtures import CONSENTS, as_guest, ensure_company, make_attendee, make_customer, make_event

ATTENDEES = [{"full_name": "Erika Mustermann", "email": "erika@ticket.example"},
	{"full_name": "Max Mustermann", "email": "max@ticket.example"}]
BILLING = {"is_company": 1, "company": "Ticket Test GmbH", "full_name": "Erika Mustermann",
	"email": "erika@ticket.example", "address_line1": "Hauptstr. 1", "postcode": "72764", "city": "Reutlingen",
	"country": "Germany"}


@patch("frappe.enqueue")
class TestTicketing(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_company()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("ticketing_test")
		self.event = make_event(max_attendees=5)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="ticketing_test")

	def order(self, attendees=ATTENDEES, billing=BILLING, consents=CONSENTS, event=None):
		with as_guest():
			return ticketing.register_attendees((event or self.event).name, attendees, billing_data=billing,
				consents=consents)

	def test_company_order_creates_lead_attendees_and_submitted_quotation(self, enqueue):
		result = self.order()
		self.assertEqual(frappe.session.user, "Administrator")
		self.assertEqual(result["reference_doctype"], "Quotation")
		qtn = frappe.get_doc("Quotation", result["reference"])
		self.assertEqual(qtn.docstatus, 1)
		self.assertEqual(qtn.quotation_to, "Lead")
		self.assertEqual(qtn.order_type, "Shopping Cart")
		self.assertEqual(len(qtn.items), 2)
		self.assertEqual(len({row.description for row in qtn.items}), 2)
		self.assertEqual(frappe.db.get_value("Lead", qtn.party_name, "company_name"), "Ticket Test GmbH")
		attendees = frappe.get_all("Attendee", filters={"quotation": qtn.name},
			fields=["email", "payment_status", "is_buyer", "contact", "quotation_item", "terms_accepted_on"])
		self.assertEqual(len(attendees), 2)
		self.assertTrue(all(a.payment_status == "Quoted" and a.contact and a.quotation_item and a.terms_accepted_on
			for a in attendees))
		self.assertEqual([a.email for a in attendees if a.is_buyer], ["erika@ticket.example"])
		self.assertTrue(frappe.db.exists("Dynamic Link", {"parenttype": "Address", "link_doctype": "Lead",
			"link_name": qtn.party_name}))
		enqueue.assert_called_once()

	def test_known_customer_gets_the_quotation(self, enqueue):
		make_customer("Known Ticket Customer AG", "erika@ticket.example")
		result = self.order(billing=None)
		qtn = frappe.get_doc("Quotation", result["reference"])
		self.assertEqual((qtn.quotation_to, qtn.party_name), ("Customer", "Known Ticket Customer AG"))

	def test_free_event_books_without_quotation(self, enqueue):
		free = make_event("Free Test Event", paid=False)
		result = self.order(event=free, billing=None)
		self.assertEqual(result["reference_doctype"], "Attendee")
		self.assertTrue(result["reference"].startswith("BK-"))
		self.assertEqual(set(frappe.get_all("Attendee", filters={"event": free.name}, pluck="payment_status")),
			{"Not Required"})

	def test_consents_are_required(self, enqueue):
		self.assertRaises(frappe.ValidationError, self.order, consents={"terms": 1})

	def test_closed_sale_is_refused(self, enqueue):
		for values in ({"registration_open": 0}, {"published": 0}, {"status": "Completed"},
				{"ticket_sales_until": add_days(now_datetime(), -1)}):
			self.event.reload()
			self.event.update(values)
			self.event.save()
			self.assertRaises(frappe.ValidationError, self.order)
			frappe.db.rollback(save_point="ticketing_test")
			self.event = make_event(max_attendees=5)

	def test_capacity_and_duplicates(self, enqueue):
		for i in range(4):
			make_attendee(self.event.name, f"seat{i}@example.com")
		self.assertRaises(frappe.ValidationError, self.order)  # 4 + 2 > 5
		frappe.db.rollback(save_point="ticketing_test")
		self.event = make_event(max_attendees=5)
		self.assertRaises(frappe.ValidationError, self.order, attendees=[ATTENDEES[0], ATTENDEES[0]])
		make_attendee(self.event.name, "erika@ticket.example")
		self.assertRaises(frappe.ValidationError, self.order)

	def test_bad_email_is_refused(self, enqueue):
		self.assertRaises(frappe.ValidationError, self.order,
			attendees=[{"full_name": "Bad", "email": "bad@example.com/"}], billing=None)

	def test_offer(self, enqueue):
		offer = ticketing.offer(self.event.name)
		self.assertTrue(offer.sale_open)
		self.assertFalse(offer.free)
		self.assertEqual(offer.spots_left, 5)
		self.assertEqual(offer.net, 100)
