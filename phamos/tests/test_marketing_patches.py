"""Patches of the Marketing module are safe to run again. bench --site <site> run-tests --module phamos.tests.test_marketing_patches"""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.patches.v1_0 import (
	migrate_attendee_legacy_data,
	migrate_event_stakeholders,
	rename_marketing_event_registration_to_attendee,
	set_event_ticket_prices,
)
from phamos.tests.marketing_fixtures import ensure_company, make_event


class TestMarketingPatches(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_company()

	def setUp(self):
		frappe.db.savepoint("patch_test")

	def tearDown(self):
		frappe.db.rollback(save_point="patch_test")

	def test_rename_is_a_no_op_when_done(self):
		rename_marketing_event_registration_to_attendee.execute()
		self.assertTrue(frappe.db.exists("DocType", "Attendee"))

	def test_legacy_rows_are_filled_once(self):
		event = make_event("Patch Test Event", paid=False).name
		name = frappe.generate_hash(length=10)
		frappe.db.sql("""insert into `tabAttendee` (name, event, full_name, email, notes, status, creation, modified)
			values (%s, %s, 'Anna Maria Alt', 'Anna@Alt.example', 'Sales Order: SO-0001', 'Registered', now(), now())""",
			(name, event))
		migrate_attendee_legacy_data.execute()
		row = frappe.db.get_value("Attendee", name, ["first_name", "last_name", "email", "source", "order_reference",
			"payment_status"], as_dict=True)
		self.assertEqual((row.first_name, row.last_name, row.email), ("Anna Maria", "Alt", "anna@alt.example"))
		self.assertEqual((row.source, row.order_reference, row.payment_status), ("Website", "SO-0001", "Pending"))
		frappe.db.set_value("Attendee", name, "source", "Import")
		migrate_attendee_legacy_data.execute()
		self.assertEqual(frappe.db.get_value("Attendee", name, "source"), "Import")

	def test_ticket_prices_from_item_price(self):
		event = make_event("Patch Price Event")
		frappe.db.delete("Marketing Event Ticket Price", {"parent": event.name})
		set_event_ticket_prices.execute()
		rows = frappe.get_all("Marketing Event Ticket Price", filters={"parent": event.name}, fields=["title", "rate"])
		self.assertEqual([(r.title, r.rate) for r in rows], [("Regular", 100)])  # the fixture's Item Price (net)
		self.assertEqual(frappe.db.get_value("Marketing Content", event.name, "ticket_price_includes_tax"), 0)
		set_event_ticket_prices.execute()
		self.assertEqual(frappe.db.count("Marketing Event Ticket Price", {"parent": event.name}), 1)

	def test_organizer_flag(self):
		ours = make_event("Patch Ours Event", paid=False, organizer_name="phamos GmbH")
		theirs = make_event("Patch Theirs Event", paid=False, organizer_name="Some Association e.V.")
		migrate_event_stakeholders.execute()
		self.assertEqual(frappe.db.get_value("Marketing Content", ours.name, "organizer_is_phamos"), 1)
		self.assertEqual(frappe.db.get_value("Marketing Content", theirs.name, "organizer_is_phamos"), 0)
