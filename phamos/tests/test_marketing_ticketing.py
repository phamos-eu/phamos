"""Website orders: validation, Customer + submitted Sales Order, prices over time, all as Guest.

bench --site <site> run-tests --module phamos.tests.test_marketing_ticketing
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, now_datetime

from phamos.marketing import billing, ticketing
from phamos.tests.marketing_fixtures import BILLING, CONTACT, as_guest, ensure_company, make_attendee, make_customer, make_event

COMPANIONS = [{"full_name": "Max Mustermann", "email": ""}]
COMPANY_BILLING = {**BILLING, "is_company": 1, "company": "Ticket Test GmbH", "vat_id": "DE123456789"}


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
		for name in frappe.get_all("Marketing Content", pluck="name"):
			frappe.cache.delete_value(ticketing._holds_key(name))  # holds live in Redis, not in the rollback
		frappe.db.rollback(save_point="ticketing_test")

	def order(self, contact=CONTACT, attends=1, companions=COMPANIONS, billing_data=COMPANY_BILLING, event=None, **kwargs):
		with as_guest():
			return ticketing.register_attendees((event or self.event).name, contact, attends=attends,
				companions=companions, billing_data=billing_data, **kwargs)

	def test_company_order_creates_customer_and_submitted_sales_order(self, enqueue):
		result = self.order()
		self.assertEqual(frappe.session.user, "Administrator")
		self.assertEqual(result["reference_doctype"], "Sales Order")
		self.assertTrue(ticketing.verify_consent_token(result["reference"], result["consent_token"]))
		so = frappe.get_doc("Sales Order", result["reference"])
		self.assertEqual(so.docstatus, 1)
		self.assertEqual(so.order_type, "Shopping Cart")
		self.assertEqual(len(so.items), 2)
		self.assertEqual(len({row.description for row in so.items}), 2)
		self.assertIn("(Regular)", so.items[0].description)
		# 119 gross incl. 19 % VAT per ticket: the consumer pays exactly the advertised price.
		self.assertEqual(flt(so.grand_total, 2), 238.0)
		self.assertEqual(flt(so.net_total, 2), 200.0)
		customer = frappe.get_doc("Customer", so.customer)
		self.assertEqual((customer.customer_type, customer.customer_name, customer.tax_id),
			("Company", "Ticket Test GmbH", "DE123456789"))
		self.assertTrue(customer.customer_primary_contact and customer.customer_primary_address)
		self.assertEqual(so.customer_address, customer.customer_primary_address)
		self.assertFalse(frappe.db.exists("Lead", {"email_id": "erika@ticket.example"}))
		rows = frappe.get_all("Attendee", filters={"sales_order": so.name},
			fields=["email", "payment_status", "is_buyer", "contact", "crm_status", "terms_accepted", "ticket_type", "notes"],
			order_by="creation asc")
		self.assertEqual([r.payment_status for r in rows], ["Ordered", "Ordered"])
		self.assertEqual([r.ticket_type for r in rows], ["Regular", "Regular"])
		self.assertTrue(all(r.terms_accepted for r in rows))
		buyer, companion = rows
		self.assertTrue(buyer.is_buyer and buyer.contact)
		self.assertFalse(companion.email or companion.contact)
		self.assertEqual(companion.crm_status, "Unlinked")
		self.assertIn("erika@ticket.example", companion.notes)
		enqueue.assert_called_once()

	def test_private_buyer_is_an_individual_customer(self, enqueue):
		result = self.order(billing_data=BILLING, companions=[])
		customer = frappe.db.get_value("Sales Order", result["reference"], "customer")
		self.assertEqual(frappe.db.get_value("Customer", customer, "customer_type"), "Individual")

	def test_known_customer_is_reused(self, enqueue):
		make_customer("Known Ticket Customer AG", "erika@ticket.example")
		result = self.order()
		self.assertEqual(frappe.db.get_value("Sales Order", result["reference"], "customer"), "Known Ticket Customer AG")
		self.assertFalse(frappe.db.exists("Customer", {"customer_name": "Ticket Test GmbH"}))

	def test_company_name_match_needs_review(self, enqueue):
		make_customer("Ticket Test GmbH")
		result = self.order()
		buyer = frappe.get_all("Attendee", filters={"sales_order": result["reference"], "is_buyer": 1},
			fields=["crm_status", "customer"])[0]
		self.assertEqual(buyer.crm_status, "Needs Review")
		self.assertNotEqual(buyer.customer, "Ticket Test GmbH")

	def test_contact_who_does_not_attend(self, enqueue):
		result = self.order(attends=0, companions=[{"full_name": "Colleague One", "email": "colleague@ticket.example"}])
		rows = frappe.get_all("Attendee", filters={"sales_order": result["reference"]}, fields=["email", "is_buyer", "customer"])
		self.assertEqual([r.email for r in rows], ["colleague@ticket.example"])
		self.assertFalse(rows[0].is_buyer)
		# A companion of a company order belongs to the company.
		self.assertEqual(rows[0].customer, frappe.db.get_value("Sales Order", result["reference"], "customer"))

	def test_early_bird_then_regular(self, enqueue):
		event = make_event("Early Bird Test Event", prices=[
			{"title": "Early Bird", "rate": 59.5, "quota": 2, "valid_until": add_days(now_datetime(), 10)},
			{"title": "Regular", "rate": 119}])
		self.assertEqual(billing.get_ticket_pricing(event, 1).price_title, "Early Bird")
		# Two early-bird tickets fit, three do not: the order gets the next price row.
		self.assertEqual(billing.get_ticket_pricing(event, 3).price_title, "Regular")
		first = self.order(event=event, billing_data=BILLING, expected_total=119)
		self.assertEqual(flt(frappe.db.get_value("Sales Order", first["reference"], "grand_total"), 2), 119.0)
		# The quota is used up: the next buyer pays the regular price, and a stale total is refused.
		self.assertEqual(billing.get_ticket_pricing(event, 1).price_title, "Regular")
		self.assertRaises(frappe.ValidationError, self.order, event=event, contact={"full_name": "Late Bird",
			"email": "late@ticket.example"}, companions=[], billing_data={**BILLING, "email": "late@ticket.example"},
			expected_total=59.5)
		# After the early-bird window everybody pays the regular price.
		later = billing.get_ticket_pricing(event, 1, now=add_days(now_datetime(), 11))
		self.assertEqual(later.price_title, "Regular")

	def test_free_event_books_without_order(self, enqueue):
		free = make_event("Free Test Event", paid=False)
		result = self.order(event=free, billing_data=None)
		self.assertEqual(result["reference_doctype"], "Attendee")
		self.assertTrue(result["reference"].startswith("BK-"))
		self.assertEqual(set(frappe.get_all("Attendee", filters={"event": free.name}, pluck="payment_status")),
			{"Not Required"})

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
		self.assertRaises(frappe.ValidationError, self.order, companions=[{"full_name": "Twin", "email": CONTACT["email"]}])
		make_attendee(self.event.name, "erika@ticket.example")
		self.assertRaises(frappe.ValidationError, self.order)

	def test_bad_email_is_refused(self, enqueue):
		self.assertRaises(frappe.ValidationError, self.order, contact={"full_name": "Bad", "email": "bad@example.com/"})

	def test_save_consents(self, enqueue):
		result = self.order()
		email = ticketing.save_consents(result["reference"], {"newsletter": 1, "public_listing": 1})
		self.assertEqual(email, "erika@ticket.example")
		buyer = frappe.get_all("Attendee", filters={"sales_order": result["reference"], "is_buyer": 1},
			fields=["newsletter_consent", "newsletter_consent_on", "public_listing_consent", "share_with_attendees_consent"])[0]
		self.assertTrue(buyer.newsletter_consent and buyer.newsletter_consent_on and buyer.public_listing_consent)
		self.assertFalse(buyer.share_with_attendees_consent)
		self.assertFalse(ticketing.verify_consent_token(result["reference"], "1.forged"))
		self.assertFalse(ticketing.verify_consent_token("SAL-ORD-OTHER", result["consent_token"]))

	def test_confirmation_job_arguments_and_email(self, enqueue):
		result = self.order()
		kwargs = enqueue.call_args.kwargs
		self.assertNotIn("event", kwargs)  # frappe.enqueue's own parameter: it would never reach the job
		job_args = {k: v for k, v in kwargs.items() if k not in ("enqueue_after_commit", "queue", "timeout", "now")}
		with patch("frappe.sendmail") as sendmail:
			ticketing.send_order_confirmation(**job_args)
		mail = sendmail.call_args.kwargs
		self.assertEqual(mail["recipients"], ["erika@ticket.example"])
		self.assertIn(result["reference"], mail["subject"])
		self.assertEqual(mail["reference_name"], result["reference"])
		self.assertTrue(any(a["fname"].endswith(".ics") for a in mail["attachments"]))

	def test_ticket_holders_with_email_get_their_own_ticket(self, enqueue):
		companions = [{"full_name": "Max Mit Mail", "email": "max@ticket.example"}, {"full_name": "Ohne Mail"}]
		self.order(companions=companions)
		jobs = [c.kwargs for c in enqueue.call_args_list]
		# The buyer's confirmation (all tickets) plus one ticket for the companion with an email.
		self.assertEqual([j["recipient"] for j in jobs if "recipient" in j], ["erika@ticket.example"])
		tickets = [j for j in jobs if j.get("attendee")]
		self.assertEqual(len(tickets), 1)
		self.assertEqual(frappe.db.get_value("Attendee", tickets[0]["attendee"], "email"), "max@ticket.example")
		job_args = {k: v for k, v in tickets[0].items() if k not in ("enqueue_after_commit", "queue", "timeout", "now")}
		with patch("frappe.sendmail") as sendmail:
			ticketing.send_ticket(**job_args)
		mail = sendmail.call_args.kwargs
		self.assertEqual(mail["recipients"], ["max@ticket.example"])
		self.assertEqual(mail["template"], "event_ticket")
		self.assertTrue(any(a["fname"].endswith(".ics") for a in mail["attachments"]))

	def test_offer(self, enqueue):
		offer = ticketing.offer(self.event.name)
		self.assertTrue(offer.sale_open)
		self.assertFalse(offer.free)
		self.assertEqual(offer.spots_left, 5)
		self.assertEqual((offer.gross, offer.net, offer.price_title), (119, 100, "Regular"))
		self.assertEqual(len(offer.prices), 1)

	def test_holds_reserve_seats_and_prices(self, enqueue):
		event = make_event("Hold Test Event", max_attendees=3, prices=[
			{"title": "Early Bird", "rate": 59.5, "quota": 2}, {"title": "Regular", "rate": 119}])
		first = ticketing.hold_seats(event, "hold-aaaaaaaa", 2)
		self.assertTrue(first["ok"])
		self.assertEqual(first["price_title"], "Early Bird")
		self.assertEqual(first["spots_left"], 1)
		# The two early-bird seats are held: the next visitor gets the regular price and one seat at most.
		self.assertEqual(ticketing.offer(event.name).spots_left, 1)
		second = ticketing.hold_seats(event, "hold-bbbbbbbb", 1)
		self.assertEqual(second["price_title"], "Regular")
		self.assertFalse(ticketing.hold_seats(event, "hold-cccccccc", 1)["ok"])  # 2 + 1 held = capacity
		# The holder orders: its own hold does not block it, and is released afterwards.
		result = self.order(event=event, billing_data=BILLING, hold_id="hold-aaaaaaaa", expected_total=119)
		self.assertEqual(frappe.db.get_value("Sales Order", result["reference"], "grand_total"), 119)
		self.assertNotIn("hold-aaaaaaaa", ticketing.active_holds(event.name))
		# An expired hold counts for nothing.
		frappe.cache.hset(ticketing._holds_key(event.name), "hold-bbbbbbbb", {"qty": 1, "price_title": "Regular",
			"expires": 0})
		self.assertEqual(ticketing.held_seats(event.name), 0)
		self.assertEqual(ticketing.offer(event.name).spots_left, 1)
