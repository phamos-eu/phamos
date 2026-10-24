"""Website orders: validation, Customer + submitted Sales Order, prices over time, all as Guest.

bench --site <site> run-tests --module phamos.tests.test_marketing_ticketing
"""

import hashlib
import hmac
import json
import uuid
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, now_datetime

from phamos.marketing import billing, ticketing
from phamos.tests.marketing_fixtures import BILLING, CONTACT, as_guest, ensure_company, make_attendee, make_customer, make_event

CONFIRMATION_JOB = "phamos.marketing.ticketing.send_order_confirmation"


def confirmations(enqueue):
	return [c for c in enqueue.call_args_list if c.args and c.args[0] == CONFIRMATION_JOB]

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
		frappe.db.after_commit.reset()  # a savepoint rollback keeps queued after-commit callbacks
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

	def test_known_email_never_uses_the_existing_customer(self, enqueue):
		# An anonymous order with a known customer's email must not land on that Customer, nor reveal its
		# stored address or VAT ID: a new Customer is created and flagged for review instead.
		known = make_customer("Known Ticket Customer AG", "erika@ticket.example")
		frappe.db.set_value("Customer", known, "tax_id", "DE999999999")
		secret = frappe.get_doc({"doctype": "Address", "address_title": known, "address_type": "Billing",
			"address_line1": "Geheimweg 7", "city": "Stuttgart", "country": "Germany",
			"links": [{"link_doctype": "Customer", "link_name": known}]}).insert(ignore_permissions=True)
		frappe.db.set_value("Customer", known, "customer_primary_address", secret.name)
		existing_contact = frappe.db.get_value("Contact Email", {"email_id": "erika@ticket.example"}, "parent")
		links_before = frappe.get_all("Dynamic Link", filters={"parenttype": "Contact", "parent": existing_contact},
			pluck="link_name")

		result = self.order()
		so = frappe.get_doc("Sales Order", result["reference"])
		self.assertNotEqual(so.customer, known)
		self.assertNotEqual(so.customer_address, secret.name)
		self.assertEqual(frappe.db.get_value("Address", so.customer_address, "address_line1"), "Hauptstr. 1")
		self.assertNotEqual(so.tax_id, "DE999999999")
		buyer = frappe.get_all("Attendee", filters={"sales_order": so.name, "is_buyer": 1}, fields=["crm_status"])[0]
		self.assertEqual(buyer.crm_status, "Needs Review")
		self.assertTrue(frappe.db.exists("Comment", {"reference_doctype": "Customer", "reference_name": so.customer,
			"content": ["like", f"%{known}%"]}))
		# The existing Contact is left alone.
		self.assertEqual(frappe.get_all("Dynamic Link", filters={"parenttype": "Contact", "parent": existing_contact},
			pluck="link_name"), links_before)

		with patch("frappe.sendmail") as sendmail:
			ticketing.send_order_confirmation(event_name=self.event.name, reference=so.name,
				recipient="erika@ticket.example", buyer_name="Erika Mustermann", lang="en")
		self.assertNotIn("Geheimweg", json.dumps(sendmail.call_args.kwargs["args"], default=str))

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

	def test_duplicate_message_names_no_address(self, enqueue):
		make_attendee(self.event.name, "erika@ticket.example")
		with self.assertRaises(frappe.ValidationError) as raised:
			self.order()
		self.assertNotIn("erika@ticket.example", str(raised.exception))

	def test_hold_is_released_only_after_commit(self, enqueue):
		self.assertTrue(ticketing.hold_seats(self.event, "hold-commit-1", 2)["ok"])
		self.order(hold_id="hold-commit-1")
		# Until the attendees are committed, the held seats must still count (phamos/phamos#1699).
		self.assertIn("hold-commit-1", ticketing.active_holds(self.event.name))
		frappe.db.after_commit.run()
		self.assertNotIn("hold-commit-1", ticketing.active_holds(self.event.name))

	def test_failed_order_keeps_its_hold(self, enqueue):
		self.assertTrue(ticketing.hold_seats(self.event, "hold-failed-1", 1)["ok"])
		for i in range(4):
			make_attendee(self.event.name, f"seat{i}@ticket.example")
		self.assertRaises(frappe.ValidationError, self.order, hold_id="hold-failed-1")  # 2 tickets, 1 seat left
		frappe.db.after_commit.run()
		self.assertIn("hold-failed-1", ticketing.active_holds(self.event.name))

	def test_repeated_order_returns_the_first_order(self, enqueue):
		# phamos/phamos#1700: double click, lost response or reload send the same hold id again.
		event = make_event("Idempotency Full Event", max_attendees=2)
		key = str(uuid.uuid4())
		first = self.order(event=event, hold_id=key)
		# The event is sold out now: the repeat must still get its order back, before any other check.
		again = self.order(event=event, hold_id=key)
		self.assertEqual((again["reference"], again["reference_doctype"], again["attendees"], again["paid"]),
			(first["reference"], "Sales Order", 2, True))
		self.assertEqual(again["tickets_to"], "erika@ticket.example")
		self.assertTrue(ticketing.verify_consent_token(first["reference"], again["consent_token"]))
		self.assertEqual(frappe.db.count("Sales Order", {"customer": frappe.db.get_value(
			"Sales Order", first["reference"], "customer"), "docstatus": 1}), 1)
		self.assertEqual(frappe.get_all("Attendee", filters={"event": event.name}, pluck="order_key"), [key, key])
		self.assertEqual(len(confirmations(enqueue)), 1)

	def test_repeated_free_order_without_companion_emails(self, enqueue):
		free = make_event("Idempotency Free Event", paid=False)
		key = str(uuid.uuid4())
		first = self.order(event=free, billing_data=None, hold_id=key)
		again = self.order(event=free, billing_data=None, hold_id=key)
		self.assertEqual((again["reference"], again["reference_doctype"], again["paid"]),
			(first["reference"], "Attendee", False))
		self.assertEqual(frappe.db.count("Attendee", {"event": free.name}), 2)
		self.assertEqual(len(confirmations(enqueue)), 1)

	def test_repeat_with_other_data_gets_the_first_order(self, enqueue):
		key = str(uuid.uuid4())
		first = self.order(hold_id=key)
		again = self.order(contact={"full_name": "Other Person", "email": "other@ticket.example"}, companions=[],
			hold_id=key)
		self.assertEqual(again["reference"], first["reference"])
		self.assertFalse(frappe.db.exists("Attendee", {"event": self.event.name, "email": "other@ticket.example"}))

	def test_short_hold_id_gets_no_idempotency(self, enqueue):
		first = self.order(hold_id="short-key-1234")
		again = self.order(contact={"full_name": "Other Person", "email": "other@ticket.example"}, companions=[],
			hold_id="short-key-1234")
		self.assertNotEqual(again["reference"], first["reference"])
		self.assertFalse(frappe.db.get_value("Attendee", {"event": self.event.name}, "order_key"))

	def test_retry_after_a_failed_order_books(self, enqueue):
		key = str(uuid.uuid4())
		self.assertRaises(frappe.ValidationError, self.order, hold_id=key, expected_total=1)  # price changed
		result = self.order(hold_id=key, expected_total=238)
		self.assertEqual(frappe.db.count("Attendee", {"event": self.event.name, "order_key": key}), 2)
		self.assertEqual(result["reference_doctype"], "Sales Order")

	def test_order_locks_the_event_row(self, enqueue):
		with patch("frappe.get_doc", wraps=frappe.get_doc) as get_doc:
			self.order()
		self.assertIn((("Marketing Content", self.event.name), {"for_update": True}),
			[(c.args, c.kwargs) for c in get_doc.call_args_list])

	def test_free_order_never_uses_a_known_contact(self, enqueue):
		known = make_customer("Known Free Customer AG", "erika@ticket.example")
		contact = frappe.db.get_value("Contact Email", {"email_id": "erika@ticket.example"}, "parent")
		free = make_event("Free Known Event", paid=False)
		self.order(event=free, billing_data=None, companions=[])
		att = frappe.get_all("Attendee", filters={"event": free.name}, fields=["name", "contact", "customer", "crm_status"])[0]
		self.assertEqual((att.contact, att.customer, att.crm_status), (None, None, "Needs Review"))
		self.assertTrue(frappe.db.exists("Comment", {"reference_doctype": "Attendee", "reference_name": att.name,
			"content": ["like", f"%{contact}%"]}))
		self.assertEqual(frappe.get_all("Dynamic Link", filters={"parenttype": "Contact", "parent": contact},
			pluck="link_name"), [known])

	def test_companion_contact_is_never_linked_to_the_buyers_customer(self, enqueue):
		known = make_customer("Known Companion Customer AG", "colleague@ticket.example")
		contact = frappe.db.get_value("Contact Email", {"email_id": "colleague@ticket.example"}, "parent")
		result = self.order(companions=[{"full_name": "Colleague Known", "email": "colleague@ticket.example"}])
		row = frappe.get_all("Attendee", filters={"sales_order": result["reference"], "is_buyer": 0},
			fields=["contact", "crm_status", "customer"])[0]
		self.assertEqual((row.contact, row.crm_status), (None, "Needs Review"))
		self.assertEqual(row.customer, frappe.db.get_value("Sales Order", result["reference"], "customer"))
		# The submitted order did not touch the existing Contact either.
		self.assertEqual(frappe.get_all("Dynamic Link", filters={"parenttype": "Contact", "parent": contact},
			pluck="link_name"), [known])

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

	def test_consent_token_is_never_signed_with_the_site_name(self, enqueue):
		# phamos/phamos#1705: without an encryption key the site name (public) must not become the key.
		exp = int(add_days(now_datetime(), 1).timestamp())
		message = f"event-consent|SAL-ORD-TEST|{exp}".encode()
		forged = f"{exp}.{hmac.new(frappe.local.site.encode(), message, hashlib.sha256).hexdigest()}"
		with patch.dict(frappe.local.conf), patch("frappe.installer.update_site_config") as update_site_config:
			frappe.local.conf.pop("encryption_key", None)
			self.assertFalse(ticketing.verify_consent_token("SAL-ORD-TEST", forged))
			update_site_config.assert_called_once()  # a key is created and stored instead
			token = ticketing.consent_token("SAL-ORD-TEST")
			self.assertTrue(ticketing.verify_consent_token("SAL-ORD-TEST", token))
			self.assertFalse(ticketing.verify_consent_token("SAL-ORD-TEST", f"{exp + 1}.{token.split('.', 1)[1]}"))

	def test_names_with_links_are_refused(self, enqueue):
		# phamos/phamos#1704: names reach strangers' inboxes, so they must not carry links.
		for name in ("visit evil.example", "Max www.x.de", "Erika https://x", "me@evil.example", "St.Pauli"):
			self.assertRaises(frappe.ValidationError, ticketing._clean_person, {"full_name": name, "email": ""}, False)
		for name in ("Dr. Müller", "J. R. R. Tolkien", "Anne-Marie O'Neill", "Ph.D. Erika Muster"):
			self.assertEqual(ticketing._clean_person({"full_name": name, "email": ""}, False).full_name, name)
		self.assertRaises(frappe.ValidationError, self.order, companions=[{"full_name": "visit evil.example", "email": ""}])

	def test_companion_ticket_mails_have_a_daily_limit(self, enqueue):
		from phamos.marketing import api

		key = frappe.cache.make_key(f"event_ticket_mails:{self.event.name}:{frappe.utils.nowdate()}")
		frappe.cache.delete(key)
		people = [make_attendee(self.event.name, f"guest{i}@ticket.example") for i in range(3)]
		try:
			with patch.dict(frappe.conf, {"event_ticket_mail_daily_limit": 2}), patch("frappe.sendmail") as sendmail, \
					patch("frappe.log_error") as log_error:
				for att in people:
					ticketing.send_ticket(att.name, buyer_name="Erika", lang="en")
				self.assertEqual(sendmail.call_count, 2)
				log_error.assert_called_once()
				self.assertTrue(frappe.db.exists("Comment", {"reference_doctype": "Attendee",
					"reference_name": people[2].name, "content": ["like", "%daily limit of 2%"]}))
				self.assertGreater(frappe.cache.ttl(key), 0)
				# Staff can send it anyway from the desk.
				self.assertEqual(api.send_ticket(people[2].name), {"sent_to": "guest2@ticket.example"})
				self.assertEqual(sendmail.call_count, 3)
		finally:
			frappe.cache.delete(key)

	def test_send_ticket_needs_write_on_that_attendee(self, enqueue):
		from phamos.marketing import api

		att = make_attendee(self.event.name, "guest@ticket.example")
		if not frappe.db.exists("User", "no-rights@ticket.example"):
			frappe.get_doc({"doctype": "User", "email": "no-rights@ticket.example", "first_name": "No Rights",
				"send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.set_user("no-rights@ticket.example")
		with patch("frappe.sendmail") as sendmail:
			self.assertRaises(frappe.PermissionError, api.send_ticket, att.name)
		sendmail.assert_not_called()

	def test_ticket_mail_has_the_opt_out_line(self, enqueue):
		att = make_attendee(self.event.name, "guest@ticket.example")
		context = {"event": self.event, "venue": None, "attendee": att, "buyer_name": "Erika", "reference": None,
			"event_url": None, "privacy_url": "", "imprint_url": ""}
		lang = frappe.local.lang
		try:
			for code, text in (("en", "know about this booking? Simply reply"), ("de", "Sie wissen nichts von dieser Buchung?")):
				frappe.local.lang = code
				self.assertIn(text, frappe.render_template("templates/emails/event_ticket.html", context))
		finally:
			frappe.local.lang = lang

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

	def test_one_visitor_cannot_hold_more_than_one_order(self, enqueue):
		event = make_event("Hold Limit Event", max_attendees=50, max_attendees_per_order=4)
		try:
			frappe.local.request_ip = "203.0.113.9"
			self.assertTrue(ticketing.hold_seats(event, "hold-limit-a", 3)["ok"])
			self.assertTrue(ticketing.hold_seats(event, "hold-limit-b", 3)["ok"])
			# Together 6 > 4 per order: the visitor's older hold made room for the new one.
			self.assertEqual(set(ticketing.active_holds(event.name)), {"hold-limit-b"})
			for i in range(30):  # a script with fresh hold ids gets no further
				ticketing.hold_seats(event, f"hold-limit-x{i:02d}", 4)
			self.assertEqual(ticketing.held_seats(event.name), 4)
			# Another visitor is not affected.
			frappe.local.request_ip = "198.51.100.4"
			self.assertTrue(ticketing.hold_seats(event, "hold-limit-c", 2)["ok"])
			self.assertEqual(ticketing.held_seats(event.name), 6)
		finally:
			frappe.local.request_ip = None

	def test_confirmation_escapes_the_typed_address(self, enqueue):
		# The buyer is anonymous: markup in the address must not reach the email as HTML (phishing link
		# sent from phamos' own mail server).
		link = '<a href="https://evil.example">Pay here</a>'
		result = self.order(billing_data={**BILLING, "address_line1": f"Hauptstr. 1 {link}"}, companions=[])
		with patch("frappe.sendmail") as sendmail:
			ticketing.send_order_confirmation(event_name=self.event.name, reference=result["reference"],
				recipient="erika@ticket.example", buyer_name="Erika Mustermann", lang="en")
		mail = sendmail.call_args.kwargs
		html = frappe.render_template(f"templates/emails/{mail['template']}.html", mail["args"])
		self.assertNotIn('href="https://evil.example"', html)
		self.assertIn("&lt;a href=", html)  # the markup reached the template and was escaped there
		self.assertIn("Hauptstr. 1", html)

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
		# The holder orders: its own hold does not block it, and is released after the commit.
		result = self.order(event=event, billing_data=BILLING, hold_id="hold-aaaaaaaa", expected_total=119)
		self.assertEqual(frappe.db.get_value("Sales Order", result["reference"], "grand_total"), 119)
		frappe.db.after_commit.run()
		self.assertNotIn("hold-aaaaaaaa", ticketing.active_holds(event.name))
		# An expired hold counts for nothing.
		frappe.cache.hset(ticketing._holds_key(event.name), "hold-bbbbbbbb", {"qty": 1, "price_title": "Regular",
			"expires": 0})
		self.assertEqual(ticketing.held_seats(event.name), 0)
		self.assertEqual(ticketing.offer(event.name).spots_left, 1)


@patch("frappe.enqueue")
class TestOrderConcurrency(FrappeTestCase):
	"""Two database connections: an order must see what another order committed while it waited for the
	event lock (phamos/phamos#1699). These tests commit, so they clean up after themselves."""

	FREE_TITLE = "Concurrency Test Free Event"
	PAID_TITLE = "Concurrency Test Paid Event"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_company()
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for title in (self.FREE_TITLE, self.PAID_TITLE):
			for name in frappe.get_all("Marketing Content", filters={"title": title}, pluck="name"):
				frappe.db.delete("Attendee", {"event": name})
				frappe.cache.delete_value(ticketing._holds_key(name))
				frappe.delete_doc("Marketing Content", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def open_snapshot(self, event):
		"""The order request's first plain read (the page data), before it takes the event lock."""
		frappe.db.sql("select name from `tabMarketing Content` where name = %s", event)

	def book_elsewhere(self, event, email, **kwargs):
		primary = frappe.local.db
		with self.secondary_connection():
			make_attendee(event, email, **kwargs)
			frappe.db.commit()
		# FrappeTestCase.secondary_connection leaves the new connection active after its first use.
		frappe.local.db = primary

	def test_order_sees_a_seat_booked_while_it_waited(self, enqueue):
		event = make_event(self.FREE_TITLE, paid=False, max_attendees=1)
		frappe.db.commit()
		self.open_snapshot(event.name)
		self.book_elsewhere(event.name, "first@ticket.example")
		with as_guest(), self.assertRaises(frappe.ValidationError):
			ticketing.register_attendees(event.name, CONTACT, attends=1, companions=[])
		frappe.db.rollback()
		self.assertEqual(frappe.db.count("Attendee", {"event": event.name}), 1)

	def test_price_quota_sees_a_ticket_booked_while_it_waited(self, enqueue):
		event = make_event(self.PAID_TITLE, max_attendees=10, prices=[
			{"title": "Early Bird", "rate": 99, "quota": 1}, {"title": "Regular", "rate": 119}])
		frappe.db.commit()
		self.open_snapshot(event.name)
		self.book_elsewhere(event.name, "first@ticket.example", ticket_type="Early Bird")
		doc = frappe.get_doc("Marketing Content", event.name, for_update=True)
		# A plain read still sees the snapshot: the early-bird ticket looks free.
		self.assertEqual(billing.get_ticket_pricing(doc).price_title, "Early Bird")
		self.assertEqual(billing.get_ticket_pricing(doc, for_update=True).price_title, "Regular")
		self.assertEqual(ticketing.sale_state(doc, for_update=True), (True, None))
