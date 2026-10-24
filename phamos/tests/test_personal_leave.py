# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""My Leave in the Personal Cockpit (phamos/phamos#1714).

Runs as an Employee-only user against real HRMS validation, with a temporary holiday list
and a leave-without-pay type (both rolled back). SOGo is patched out, because Phase 2 mirrors
every Leave Application as a calendar Event.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import personal_leave
from phamos.mailcow_integration.caldav import client
from phamos.tests.test_mailcow_sync_event import _ensure_status_field, _ensure_user
from phamos.tests.test_personal_checkin import _ensure_employee

ME = "pl-me@example.com"
COLLEAGUE = "pl-colleague@example.com"
APPROVER = "pl-approver@example.com"
NO_EMPLOYEE = "pl-nobody@example.com"
LEAVE_TYPE = "PL Test Unpaid"


def _response(status):
	return SimpleNamespace(status_code=status, text="")


def _ensure_cover_field():
	"""The fixture adds `custom_cover_employee`; a site not migrated yet gets it here."""
	meta = frappe.get_meta("Leave Application")
	if meta.has_field("custom_cover_employee"):
		if not meta.get_field("custom_cover_employee").ignore_user_permissions:
			frappe.db.set_value(
				"Custom Field", "Leave Application-custom_cover_employee", "ignore_user_permissions", 1
			)
			frappe.clear_cache(doctype="Leave Application")
		return
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Leave Application": [
				{
					"fieldname": "custom_cover_employee",
					"label": "Covered by",
					"fieldtype": "Link",
					"options": "Employee",
					"insert_after": "leave_approver_name",
					"ignore_user_permissions": 1,
				}
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Leave Application")


@unittest.skipUnless(frappe.db.exists("DocType", "Leave Application"), "HRMS is not installed")
class TestPersonalLeave(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for user in (ME, COLLEAGUE, APPROVER, NO_EMPLOYEE):
			_ensure_user(user)
		# Employee-only: no System Manager, so document permissions really apply
		for user in (ME, COLLEAGUE):
			doc = frappe.get_doc("User", user)
			doc.remove_roles("System Manager", "HR Manager", "HR User")
		frappe.get_doc("User", APPROVER).add_roles("Leave Approver")
		_ensure_status_field()
		_ensure_cover_field()
		self.me = _ensure_employee(ME)
		self.colleague = _ensure_employee(COLLEAGUE)
		holiday_list = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "PL Test Holidays",
				"from_date": "2026-01-01",
				"to_date": "2027-12-31",
			}
		).insert(ignore_permissions=True, ignore_if_duplicate=True)
		for employee in (self.me, self.colleague):
			frappe.db.set_value(
				"Employee", employee, {"holiday_list": holiday_list.name, "leave_approver": APPROVER}
			)
		if not frappe.db.exists("Leave Type", LEAVE_TYPE):
			frappe.get_doc(
				{"doctype": "Leave Type", "leave_type_name": LEAVE_TYPE, "is_lwp": 1}
			).insert(ignore_permissions=True)
		frappe.db.set_single_value("HR Settings", "restrict_backdated_leave_application", 0)
		for patcher in (
			patch.object(client.requests, "put", MagicMock(return_value=_response(201))),
			patch.object(client.requests, "delete", MagicMock(return_value=_response(204))),
			patch.object(client, "settings", lambda: SimpleNamespace(base_url="https://mail.example.com")),
			patch.object(client, "dav_password", lambda email: "pw"),
		):
			patcher.start()
			self.addCleanup(patcher.stop)
		frappe.flags.mailcow_sync_now = True
		self.addCleanup(setattr, frappe.flags, "mailcow_sync_now", False)
		frappe.set_user(ME)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _apply(self, **values):
		args = {"leave_type": LEAVE_TYPE, "from_date": "2026-11-03", "to_date": "2026-11-04", **values}
		return personal_leave.apply_leave(**args)

	# --- applying ----------------------------------------------------------------------------

	def test_apply_creates_open_unsubmitted_leave_for_my_approver(self):
		row = self._apply(cover_employee=self.colleague, description="Family visit")
		doc = frappe.get_doc("Leave Application", row["name"])
		self.assertEqual(doc.employee, self.me)
		self.assertEqual(doc.status, "Open")
		self.assertEqual(doc.docstatus, 0)
		self.assertEqual(doc.leave_approver, APPROVER)
		self.assertEqual(doc.custom_cover_employee, self.colleague)
		self.assertTrue(row["editable"])
		self.assertEqual(row["calendar"]["state"], "synced")  # Phase 2 put it in my calendar

	def test_hrms_validation_reaches_the_caller(self):
		self._apply()
		with self.assertRaises(frappe.ValidationError) as ctx:
			self._apply(from_date="2026-11-04", to_date="2026-11-05")
		self.assertIn("already applied", str(ctx.exception))

	def test_cover_stays_empty_unless_chosen(self):
		# an Employee user permission must not default "Covered by" to the applicant
		row = self._apply()
		self.assertIsNone(frappe.db.get_value("Leave Application", row["name"], "custom_cover_employee"))

	def test_nobody_covers_for_themselves(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			self._apply(cover_employee=self.me)
		self.assertIn("cover for yourself", str(ctx.exception))

	def test_dates_are_required(self):
		with self.assertRaises(frappe.ValidationError):
			personal_leave.apply_leave(LEAVE_TYPE, None, "2026-11-04")

	# --- reading -----------------------------------------------------------------------------

	def test_list_shows_only_my_leave_newest_first_with_a_status_filter(self):
		older = self._apply(from_date="2026-10-05", to_date="2026-10-05")
		newer = self._apply(from_date="2026-12-07", to_date="2026-12-08")
		frappe.set_user(COLLEAGUE)
		theirs = self._apply()
		frappe.set_user(ME)
		names = [r["name"] for r in personal_leave.get_my_leave()["leave"]]
		self.assertEqual(names, [newer["name"], older["name"]])
		self.assertNotIn(theirs["name"], names)
		self.assertEqual(len(personal_leave.get_my_leave(status="Open")["leave"]), 2)
		self.assertEqual(personal_leave.get_my_leave(status="Approved")["leave"], [])

	def test_someone_elses_entry_is_refused(self):
		frappe.set_user(COLLEAGUE)
		theirs = self._apply()
		frappe.set_user(ME)
		with self.assertRaises(frappe.PermissionError):
			personal_leave.get_my_leave_entry(theirs["name"])

	def test_form_options_offer_without_pay_types_and_my_approver(self):
		options = personal_leave.get_leave_form_options("2026-11-03")
		self.assertEqual(options["leave_approver"], APPROVER)
		types = {t["value"]: t for t in options["leave_types"]}
		self.assertTrue(types[LEAVE_TYPE]["without_pay"])
		covers = [c["value"] for c in options["cover_employees"]]
		self.assertIn(self.colleague, covers)
		self.assertNotIn(self.me, covers)

	def test_user_without_employee_gets_no_leave(self):
		frappe.set_user(NO_EMPLOYEE)
		self.assertEqual(personal_leave.get_my_leave(), {"has_employee": False, "leave": []})
		self.assertFalse(personal_leave.get_my_leave_balance()["has_employee"])
		with self.assertRaises(frappe.ValidationError):
			self._apply()

	# --- editing and withdrawing ------------------------------------------------------------

	def test_update_changes_my_open_leave(self):
		row = self._apply()
		updated = personal_leave.update_leave(
			row["name"], LEAVE_TYPE, "2026-11-03", "2026-11-06", modified=row["modified"]
		)
		self.assertEqual(updated["to_date"], "2026-11-06")
		self.assertEqual(frappe.db.get_value("Leave Application", row["name"], "to_date").isoformat(), "2026-11-06")

	def test_update_refuses_a_stale_copy(self):
		row = self._apply()
		personal_leave.update_leave(row["name"], LEAVE_TYPE, "2026-11-03", "2026-11-05")
		with self.assertRaises(frappe.ValidationError):
			personal_leave.update_leave(row["name"], LEAVE_TYPE, "2026-11-03", "2026-11-06", modified=row["modified"])

	def test_decided_or_foreign_leave_cannot_be_changed(self):
		row = self._apply()
		frappe.set_user("Administrator")
		frappe.db.set_value("Leave Application", row["name"], "status", "Approved")
		frappe.set_user(COLLEAGUE)
		theirs = self._apply()
		frappe.set_user(ME)
		for name in (row["name"], theirs["name"]):
			with self.assertRaises(frappe.PermissionError):
				personal_leave.update_leave(name, LEAVE_TYPE, "2026-11-03", "2026-11-05")
			with self.assertRaises(frappe.PermissionError):
				personal_leave.withdraw_leave(name)

	def test_withdraw_deletes_my_open_leave_and_its_event(self):
		row = self._apply()
		self.assertTrue(
			frappe.db.exists("Event", {"reference_doctype": "Leave Application", "reference_docname": row["name"]})
		)
		self.assertEqual(personal_leave.withdraw_leave(row["name"]), {"name": row["name"], "withdrawn": True})
		self.assertFalse(frappe.db.exists("Leave Application", row["name"]))
		self.assertFalse(
			frappe.db.exists("Event", {"reference_doctype": "Leave Application", "reference_docname": row["name"]})
		)
