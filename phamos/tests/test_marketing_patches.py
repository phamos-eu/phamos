"""Patches of the Marketing module are safe to run again. bench --site <site> run-tests --module phamos.tests.test_marketing_patches"""

import io
from contextlib import redirect_stdout

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from phamos.patches.v1_0 import (
	migrate_attendee_legacy_data,
	migrate_event_stakeholders,
	rename_marketing_event_registration_to_attendee,
	repair_legacy_attendees,
	set_event_ticket_prices,
)
from phamos.marketing import billing
from phamos.tests.marketing_fixtures import ensure_company, make_customer, make_event, make_ticket_item


def legacy_row(event, email, order_reference=None, **values):
	"""An Attendee row as the old registration left it (written directly, like migrate_attendee_legacy_data)."""
	name = frappe.generate_hash(length=10)
	frappe.db.sql("""insert into `tabAttendee` (name, event, first_name, last_name, email, order_reference, status,
		payment_status, creation, modified) values (%s, %s, 'Legacy', 'Person', %s, %s, 'Registered', 'Pending', now(), now())""",
		(name, event, email, order_reference))
	if values:
		frappe.db.set_value("Attendee", name, values, update_modified=False)
	return name


def legacy_order(event, emails, submit=True):
	"""A ticket Sales Order of the old registration: po_no "Ticket purchase for <event> ...", one line per person."""
	so = frappe.new_doc("Sales Order")
	so.customer = make_customer("Legacy Order Customer AG")
	so.company = billing.default_company()
	so.transaction_date = so.delivery_date = nowdate()
	so.po_no = f"Ticket purchase for {event} 2026-07-01 10:00:00"
	for email in emails:
		so.append("items", {"item_code": make_ticket_item(), "qty": 1, "rate": 100, "delivery_date": nowdate(),
			"additional_notes": f"Legacy Person\n{email}"})
	so.insert(ignore_permissions=True)
	if submit:
		so.submit()
	return so


def run_repair():
	with redirect_stdout(io.StringIO()) as out:
		repair_legacy_attendees.execute()
	return out.getvalue()


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

	# --- repair_legacy_attendees (phamos/phamos#1713) --------------------------------------------------------

	def test_submitted_legacy_order_is_linked_with_its_invoice_status(self):
		event = make_event("Repair Paid Event").name
		so = legacy_order(event, ["one@legacy.example", "two@legacy.example"])
		billing.make_sales_invoice(so.name, submit=True)
		second = legacy_row(event, "two@legacy.example", so.name)
		first = legacy_row(event, "one@legacy.example", so.name)
		run_repair()
		for name, line in ((first, so.items[0].name), (second, so.items[1].name)):
			row = frappe.db.get_value("Attendee", name, ["sales_order", "sales_order_item", "payment_status"], as_dict=True)
			self.assertEqual((row.sales_order, row.sales_order_item, row.payment_status), (so.name, line, "Invoiced"))

	def test_draft_legacy_order_is_only_listed(self):
		event = make_event("Repair Draft Event").name
		so = legacy_order(event, ["draft@legacy.example"], submit=False)
		name = legacy_row(event, "draft@legacy.example", so.name)
		self.assertIn(f"draft order {so.name}", run_repair())
		self.assertEqual(frappe.db.get_value("Attendee", name, ["sales_order", "payment_status"]), (None, "Pending"))

	def test_free_event_rows_are_not_required(self):
		free = make_event("Repair Free Event", paid=False).name
		paid = make_event("Repair Unpaid Event").name
		free_row, paid_row = legacy_row(free, "free@legacy.example"), legacy_row(paid, "unpaid@legacy.example")
		run_repair()
		self.assertEqual(frappe.db.get_value("Attendee", free_row, "payment_status"), "Not Required")
		self.assertEqual(frappe.db.get_value("Attendee", paid_row, "payment_status"), "Pending")

	def test_duplicates_keep_the_row_with_an_order(self):
		event = make_event("Repair Duplicate Event", paid=False).name
		older = legacy_row(event, "twice@legacy.example")
		ordered = legacy_row(event, "twice@legacy.example", "FREE-0001")
		run_repair()
		self.assertEqual(frappe.db.get_value("Attendee", ordered, "status"), "Registered")
		self.assertEqual(frappe.db.get_value("Attendee", older, "status"), "Cancelled")
		self.assertIn(f"Duplicate of {ordered}", frappe.db.get_value("Attendee", older, "notes"))
		frappe.get_doc("Attendee", ordered).save()  # saving works again

	def test_invalid_email_moves_to_the_notes(self):
		event = make_event("Repair Email Event", paid=False).name
		name = legacy_row(event, "not an email")
		run_repair()
		self.assertEqual(frappe.db.get_value("Attendee", name, "email"), None)
		self.assertIn("Email from the old form: not an email", frappe.db.get_value("Attendee", name, "notes"))
		frappe.get_doc("Attendee", name).save()

	def test_group_registrations(self):
		upcoming = make_event("Repair Group Event", paid=False).name
		past = make_event("Repair Past Group Event", paid=False, starts_on=add_days(nowdate(), -30),
			ends_on=add_days(nowdate(), -30)).name
		group = legacy_row(upcoming, "group@legacy.example", number_of_attendees=3)
		old = legacy_row(past, "old@legacy.example", number_of_attendees=3)
		output = run_repair()
		self.assertEqual(frappe.db.count("Attendee", {"event": upcoming, "status": "Registered"}), 3)
		self.assertEqual(frappe.db.get_value("Attendee", group, "number_of_attendees"), 1)
		self.assertEqual(frappe.db.count("Attendee", {"event": past}), 1)
		self.assertIn(f"{old}: past event", output)

	def test_repair_runs_twice_without_changes(self):
		event = make_event("Repair Twice Event", paid=False).name
		legacy_row(event, "twice@legacy.example")
		legacy_row(event, "twice@legacy.example")
		legacy_row(event, "group@legacy.example", number_of_attendees=2)
		run_repair()
		self.assertEqual(run_repair(), "")

