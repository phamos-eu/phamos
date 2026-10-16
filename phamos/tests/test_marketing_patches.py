"""Patches of the Marketing module are safe to run again. bench --site <site> run-tests --module phamos.tests.test_marketing_patches"""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.patches.v1_0 import migrate_attendee_legacy_data, rename_marketing_event_registration_to_attendee
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
