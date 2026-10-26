"""The former "Event Ticketing" service user: its patches remove the user, the role and the permission copies
(phamos/phamos#1708, #1726). bench --site <site> run-tests --module phamos.tests.test_marketing_setup
"""

import io
from contextlib import redirect_stdout
from unittest.mock import patch

import frappe
from frappe.permissions import add_permission, setup_custom_perms
from frappe.tests.utils import FrappeTestCase

from phamos.marketing import setup, ticketing
from phamos.patches.v1_0 import remove_event_ticketing_user, remove_unneeded_ticketing_permissions
from phamos.tests.marketing_fixtures import BILLING, CONTACT, ensure_company, make_event


def clear(*doctypes):
	for doctype in doctypes:
		frappe.clear_cache(doctype=doctype)
	frappe.clear_cache(user=setup.TICKETING_USER)


def run(patch_module):
	with redirect_stdout(io.StringIO()) as out:
		patch_module.execute()
	return out.getvalue()


@patch("frappe.enqueue")
class TestTicketingRole(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		ensure_company()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("ticketing_role_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="ticketing_role_test")
		clear(*setup.FORMER_TICKETING_DOCTYPES, *setup.TICKETING_DOCTYPES)

	def ensure_role(self):
		if not frappe.db.exists("Role", setup.TICKETING_ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": setup.TICKETING_ROLE, "desk_access": 0, "is_custom": 1}).insert(
				ignore_permissions=True)

	def make_service_user(self):
		"""The state before #1726: the role with Item read and Account select (on copies of the standard
		permissions), the user, and a Lead it owns."""
		self.ensure_role()
		for doctype, ptype in (("Item", "read"), ("Account", "select")):
			frappe.db.delete("Custom DocPerm", {"parent": doctype})
			setup_custom_perms(doctype)
			add_permission(doctype, setup.TICKETING_ROLE, permlevel=0, ptype=ptype)
		if not frappe.db.exists("User", setup.TICKETING_USER):
			user = frappe.get_doc({"doctype": "User", "email": setup.TICKETING_USER, "first_name": "Event Ticketing",
				"user_type": "Website User", "send_welcome_email": 0, "roles": [{"role": setup.TICKETING_ROLE}]})
			user.flags.no_welcome_mail = True
			user.insert(ignore_permissions=True)
		lead = frappe.get_doc({"doctype": "Lead", "first_name": "Service", "lead_name": "Service Owned",
			"email_id": "service.owned@ticket.example", "lead_owner": setup.TICKETING_USER}).insert(ignore_permissions=True)
		clear("Item", "Account")
		return lead.name

	def test_patch_removes_user_role_and_permission_rows(self, enqueue):
		lead = self.make_service_user()
		out = run(remove_event_ticketing_user)
		self.assertIn("Lead Owner set to Guest on 1 Lead(s)", out)
		self.assertIn("Item: removed 1 Event Ticketing row(s) and the untouched copy", out)
		self.assertIn(f"User {setup.TICKETING_USER} deleted", out)
		self.assertFalse(frappe.db.exists("User", setup.TICKETING_USER))
		self.assertFalse(frappe.db.exists("Role", setup.TICKETING_ROLE))
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"role": setup.TICKETING_ROLE}))
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": ["in", ["Item", "Account"]]}))
		self.assertEqual(frappe.db.get_value("Lead", lead, "lead_owner"), "Guest")
		self.assertEqual(run(remove_event_ticketing_user), "")  # a second run changes nothing

	def test_patch_keeps_a_user_that_is_still_linked(self, enqueue):
		lead = self.make_service_user()
		opportunity = frappe.get_doc({"doctype": "Opportunity", "opportunity_from": "Lead", "party_name": lead,
			"opportunity_owner": setup.TICKETING_USER}).insert(ignore_permissions=True)
		out = run(remove_event_ticketing_user)
		self.assertIn(f"{setup.TICKETING_USER} kept, still linked", out)
		self.assertIn(opportunity.name, out)
		self.assertTrue(frappe.db.exists("User", setup.TICKETING_USER))
		self.assertTrue(frappe.db.exists("Role", setup.TICKETING_ROLE))
		self.assertEqual(frappe.db.get_value("Lead", lead, "lead_owner"), "Guest")

	def test_portal_user_orders_in_their_own_session(self, enqueue):
		# No service user (phamos/phamos#1726): the order runs and is recorded as the logged-in portal user.
		portal = "portal.own@ticket.example"
		if not frappe.db.exists("User", portal):
			frappe.get_doc({"doctype": "User", "email": portal, "first_name": "Portal", "user_type": "Website User",
				"send_welcome_email": 0}).insert(ignore_permissions=True)
		event = make_event("Own Session Event")
		frappe.set_user(portal)
		result = ticketing.register_attendees(event.name, CONTACT, companions=[],
			billing_data={**BILLING, "is_company": 1, "company": "Own Session GmbH"})
		self.assertEqual(frappe.session.user, portal)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Event Ticket Order", result["reference"], "owner"), portal)
		buyer = frappe.db.get_value("Attendee", {"ticket_order": result["reference"], "is_buyer": 1}, "name")
		self.assertFalse(frappe.db.exists("Comment", {"reference_doctype": "Attendee", "reference_name": buyer}))

	def copy_with_role(self, doctype):
		"""The state before #1708: the standard permissions copied, plus the role's read row."""
		frappe.db.delete("Custom DocPerm", {"parent": doctype})
		setup_custom_perms(doctype)
		self.ensure_role()
		add_permission(doctype, setup.TICKETING_ROLE, permlevel=0, ptype="read")
		clear(doctype)

	def run_patch(self):
		return run(remove_unneeded_ticketing_permissions)

	def test_patch_removes_an_untouched_copy(self, enqueue):
		self.copy_with_role("UOM")
		self.assertIn("UOM: removed 1 Event Ticketing row(s) and the untouched copy", self.run_patch())
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": "UOM"}))
		self.assertEqual(self.run_patch().count("UOM"), 0)  # a second run changes nothing

	def test_patch_keeps_a_customised_copy(self, enqueue):
		self.copy_with_role("Currency")
		row = frappe.get_all("Custom DocPerm", filters={"parent": "Currency", "role": ["!=", setup.TICKETING_ROLE]},
			pluck="name", limit=1)[0]
		frappe.db.set_value("Custom DocPerm", row, "export", 1 - (frappe.db.get_value("Custom DocPerm", row, "export") or 0))
		self.assertIn("Currency: removed 1 Event Ticketing row(s); kept", self.run_patch())
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": "Currency", "role": setup.TICKETING_ROLE}))
		self.assertTrue(frappe.db.exists("Custom DocPerm", {"parent": "Currency"}))
