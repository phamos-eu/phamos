"""Attendee doctype rules and permissions. bench --site <site> run-tests --module phamos.tests.test_marketing_attendee"""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.tests.marketing_fixtures import ensure_company, make_attendee, make_event


class TestAttendee(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_company()
		cls.event = make_event(paid=False).name

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("attendee_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="attendee_test")

	def test_email_is_normalised_and_name_built(self):
		att = make_attendee(self.event, "  Anna.Muster@Example.COM ", "Anna", "Muster")
		self.assertEqual(att.email, "anna.muster@example.com")
		self.assertEqual(att.full_name, "Anna Muster")
		self.assertTrue(att.registered_on)

	def test_email_is_optional_for_companions(self):
		first = make_attendee(self.event, None, "Plus", "One")
		second = make_attendee(self.event, "", "Plus", "Two")
		self.assertIsNone(first.email)
		self.assertIsNone(second.email)

	def test_invalid_email_is_rejected(self):
		self.assertRaises(frappe.ValidationError, make_attendee, self.event, "anna@example.com/")

	def test_duplicate_per_event_is_rejected_unless_cancelled(self):
		first = make_attendee(self.event, "dup@example.com")
		self.assertRaises(frappe.DuplicateEntryError, make_attendee, self.event, "dup@example.com")
		first.status = "Cancelled"
		first.save()
		make_attendee(self.event, "dup@example.com")

	def test_consents_are_stamped(self):
		att = make_attendee(self.event, "consent@example.com", newsletter_consent=1)
		self.assertTrue(att.newsletter_consent_on)
		self.assertFalse(att.public_listing_consent_on)
		att.newsletter_consent = 0
		att.save()
		self.assertFalse(att.newsletter_consent_on)

	def test_attendance_stamps_check_in(self):
		att = make_attendee(self.event, "came@example.com")
		att.status = "Attended"
		att.save()
		self.assertTrue(att.checked_in_on)
		self.assertEqual(att.checked_in_by, "Administrator")

	def test_speakers_and_free_tickets_need_no_payment(self):
		self.assertEqual(make_attendee(self.event, "speaker@example.com", role="Speaker").payment_status, "Not Required")
		self.assertEqual(make_attendee(self.event, "free@example.com", ticket_type="Free").payment_status, "Not Required")
		self.assertEqual(make_attendee(self.event, "guest@example.com").payment_status, "Pending")

	def test_guests_cannot_read_or_create_attendees(self):
		roles = {p.role for p in frappe.get_meta("Attendee").permissions}
		self.assertFalse(roles & {"Guest", "All"})
		self.assertFalse(frappe.has_permission("Attendee", "read", user="Guest"))
		self.assertFalse(frappe.has_permission("Attendee", "create", user="Guest"))

	def test_registration_web_form_and_old_doctype_are_gone(self):
		self.assertFalse(frappe.db.exists("Web Form", "event-registration"))
		self.assertFalse(frappe.db.exists("DocType", "Marketing Event Registration"))
		self.assertFalse(frappe.db.exists("DocType", "Marketing Event Response"))
		self.assertEqual(frappe.db.get_value("DocType", "Marketing Content", "module"), "Marketing")
