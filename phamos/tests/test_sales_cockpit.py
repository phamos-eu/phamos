# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for the Sales cockpit API.

Focused on the guards rather than the happy path: the filter shapes the
endpoints send to the database and the rules they enforce — the class of bug
that is invisible in a manual click-through.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.sales_leads import _thread_key


class TestThreadKey(FrappeTestCase):
	"""Grouping a conversation in the feed."""

	def test_stacked_reply_prefixes_collapse(self):
		self.assertEqual(_thread_key("AW: Re: Fwd: Angebot"), _thread_key("Angebot"))

	def test_unrelated_subjects_stay_apart(self):
		self.assertNotEqual(_thread_key("Angebot"), _thread_key("Rechnung"))


class TestLeadCommunications(FrappeTestCase):
	"""A Communication reaches a Lead two ways and the feed must read both."""

	def test_merges_reference_and_link_routes(self):
		"""Inbound mail matched to a lead by address arrives through the
		Communication Link child table, not the reference fields. Querying only
		the reference fields silently hid most of a real conversation."""
		from phamos.api.sales_leads import _lead_communications

		by_reference = [{"name": "C-1", "communication_date": "2026-01-02 10:00:00"}]
		by_link = [{"name": "C-2", "communication_date": "2026-01-03 10:00:00"}]

		calls = []

		def fake_get_all(doctype, **kwargs):
			calls.append((doctype, kwargs))
			if doctype == "Communication" and "filters" in kwargs:
				filters = kwargs["filters"]
				if filters.get("reference_doctype") == "Lead":
					return by_reference
				return by_link
			if doctype == "Communication Link":
				return ["C-2"]
			return []

		with patch("frappe.get_all", side_effect=fake_get_all):
			rows = _lead_communications("LEAD-1", fields=["name", "communication_date"], limit=20)

		self.assertEqual([r["name"] for r in rows], ["C-2", "C-1"], "newest first, both routes")
		queried = [c[0] for c in calls]
		self.assertIn("Communication Link", queried)

	def test_deduplicates_a_communication_on_both_routes(self):
		from phamos.api.sales_leads import _lead_communications

		row = {"name": "C-1", "communication_date": "2026-01-02 10:00:00"}

		def fake_get_all(doctype, **kwargs):
			if doctype == "Communication Link":
				return ["C-1"]
			return [row]

		with patch("frappe.get_all", side_effect=fake_get_all):
			rows = _lead_communications("LEAD-1", fields=["name", "communication_date"], limit=20)

		self.assertEqual(len(rows), 1)


class TestLeadCommunicationTypes(FrappeTestCase):
	def test_only_emails_reach_the_feed(self):
		"""Automated messages and other Communication types are not emails."""
		from phamos.api.sales_leads import _lead_communications

		seen = []

		def fake_get_all(doctype, **kwargs):
			if doctype == "Communication":
				seen.append(kwargs["filters"])
			if doctype == "Communication Link":
				return ["C-9"]
			return []

		with patch("frappe.get_all", side_effect=fake_get_all):
			_lead_communications("LEAD-1", fields=["name"], limit=20)

		self.assertEqual(len(seen), 2)
		for filters in seen:
			self.assertEqual(filters.get("communication_type"), "Communication")


def _resolves_to(address):
	return patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", (address, 0))])


class TestWebsiteGuards(FrappeTestCase):
	"""The website check fetches a user-supplied URL from the server."""

	def test_refuses_non_public_addresses(self):
		from phamos.api.sales_leads import _is_public_http_url

		for address in ("127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "100.100.100.200", "::1"):
			with self.subTest(address=address), _resolves_to(address):
				self.assertFalse(_is_public_http_url("https://example.com"))

	def test_allows_a_public_address(self):
		from phamos.api.sales_leads import _is_public_http_url

		with _resolves_to("93.184.216.34"):
			self.assertTrue(_is_public_http_url("https://example.com"))
			self.assertTrue(_is_public_http_url("http://example.com:80/path"))

	def test_refuses_other_ports_and_schemes(self):
		from phamos.api.sales_leads import _is_public_http_url

		with _resolves_to("93.184.216.34"):
			self.assertFalse(_is_public_http_url("https://example.com:8080"))
			self.assertFalse(_is_public_http_url("ftp://example.com"))

	def test_frame_ancestors(self):
		from phamos.api.sales_leads import _frame_ancestors_allow_embedding as allows

		self.assertTrue(allows(None))
		self.assertTrue(allows("default-src 'self'"))
		self.assertTrue(allows("frame-ancestors *"))
		self.assertFalse(allows("frame-ancestors 'self'"))
		self.assertFalse(allows("frame-ancestors 'none'"))
		# Two CSP headers joined by requests: the second one forbids framing.
		self.assertFalse(allows("default-src *, frame-ancestors 'none'"))

	def test_never_frames_this_site_itself(self):
		"""The dialog's sandbox allows scripts and same-origin, which is only
		safe for pages on another origin."""
		from phamos.api import sales_leads

		with patch.object(sales_leads, "get_url", return_value="https://erp.example.com"):
			self.assertTrue(sales_leads._is_own_site("https://ERP.example.com/app/lead"))
			self.assertFalse(sales_leads._is_own_site("https://example.com"))


class TestLeadOwnerQuery(FrappeTestCase):
	def test_sales_users_come_first_but_anyone_can_be_picked(self):
		from phamos.api import sales_leads

		users = [
			frappe._dict(name="anna@example.com", full_name="Anna"),
			frappe._dict(name="ben@example.com", full_name="Ben"),
			frappe._dict(name="carla@example.com", full_name="Carla"),
		]
		with (
			patch.object(sales_leads, "_check_lead_access"),
			patch.object(sales_leads, "role_shortlist_users", return_value=[{"name": "carla@example.com"}]),
			patch("frappe.get_all", return_value=list(users)) as get_all,
		):
			rows = sales_leads.lead_owner_query("User", "", "name", 0, 20, {})

		self.assertEqual([r[0] for r in rows], ["carla@example.com", "anna@example.com", "ben@example.com"])
		filters = get_all.call_args.kwargs["filters"]
		self.assertEqual(filters["enabled"], 1)
		self.assertEqual(filters["user_type"], "System User")


class TestGetLeads(FrappeTestCase):
	def test_undated_leads_sort_first(self):
		"""Leads with no follow-up date need triage, so they lead the list."""
		from phamos.api import sales_leads

		with (
			patch.object(sales_leads, "_check_lead_access"),
			patch("frappe.get_list", return_value=[]) as get_list,
		):
			sales_leads.get_leads()

		_, kwargs = get_list.call_args
		self.assertEqual(
			kwargs["order_by"], "custom_next_followup is null desc, custom_next_followup asc"
		)
		self.assertEqual(kwargs["filters"], {"disabled": 0})

	def test_respects_user_permissions(self):
		"""get_all skips User Permissions, so a rep restricted to one Territory
		would see every lead. The list must go through get_list."""
		from phamos.api import sales_leads

		with (
			patch.object(sales_leads, "_check_lead_access"),
			patch("frappe.get_list", return_value=[]) as get_list,
			patch("frappe.get_all", return_value=[]) as get_all,
		):
			sales_leads.get_leads()

		get_list.assert_called_once()
		self.assertFalse(
			[c for c in get_all.call_args_list if c.args and c.args[0] == "Lead"],
			"the Lead list must not bypass permissions",
		)

	def test_marks_overdue_only_after_the_due_date(self):
		from phamos.api.sales_leads import _serialize_lead_row

		today = frappe.utils.getdate("2026-11-12")
		due_today = _serialize_lead_row({"custom_next_followup": "2026-11-12"}, {}, {}, today)
		due_before = _serialize_lead_row({"custom_next_followup": "2026-11-11"}, {}, {}, today)
		self.assertFalse(due_today["overdue"])
		self.assertTrue(due_before["overdue"])


class TestUpdateLead(FrappeTestCase):
	def _doc(self, modified="2026-11-12 10:00:00"):
		doc = MagicMock()
		doc.modified = modified
		doc.custom_status_comment = ""
		return doc

	def test_flags_a_stale_save_as_a_conflict(self):
		"""Someone else saved since the client loaded: the save goes through
		(autosave, not a lock) but the caller is told, so it can warn."""
		from phamos.api import sales_leads

		doc = self._doc()
		with (
			patch.object(sales_leads, "_check_lead_access"),
			patch("frappe.has_permission"),
			patch("frappe.get_doc", return_value=doc),
			patch.object(sales_leads, "get_lead", return_value={"name": "LEAD-1"}),
		):
			result = sales_leads.update_lead(
				"LEAD-1", status="Open", if_modified="2026-11-12 09:00:00"
			)

		self.assertTrue(result["conflict"])
		doc.save.assert_called_once()

	def test_a_current_save_is_not_a_conflict(self):
		from phamos.api import sales_leads

		doc = self._doc()
		with (
			patch.object(sales_leads, "_check_lead_access"),
			patch("frappe.has_permission"),
			patch("frappe.get_doc", return_value=doc),
			patch.object(sales_leads, "get_lead", return_value={"name": "LEAD-1"}),
		):
			result = sales_leads.update_lead(
				"LEAD-1", status="Open", if_modified="2026-11-12 10:00:00"
			)

		self.assertFalse(result["conflict"])

	def test_a_changed_status_comment_is_stamped(self):
		from phamos.api import sales_leads

		doc = self._doc()
		with (
			patch.object(sales_leads, "_check_lead_access"),
			patch("frappe.has_permission"),
			patch("frappe.get_doc", return_value=doc),
			patch.object(sales_leads, "get_lead", return_value={}),
		):
			sales_leads.update_lead("LEAD-1", custom_status_comment="Budget frozen")

		set_fields = {c.args[0] for c in doc.set.call_args_list}
		self.assertIn("custom_status_comment_modified_by", set_fields)
		self.assertIn("custom_status_comment_modified_date", set_fields)

	def test_nothing_to_update_is_refused(self):
		from phamos.api import sales_leads

		with (
			patch.object(sales_leads, "_check_lead_access"),
			patch("frappe.has_permission"),
			patch("frappe.get_doc", return_value=self._doc()),
		):
			with self.assertRaises(frappe.ValidationError):
				sales_leads.update_lead("LEAD-1")

	def test_needs_a_sales_role(self):
		from phamos.api import sales_leads

		with patch("frappe.has_permission"), patch("frappe.get_roles", return_value=["Employee"]), patch(
			"frappe.session", SimpleNamespace(user="someone@example.com")
		):
			with self.assertRaises(frappe.PermissionError):
				sales_leads.update_lead("LEAD-1", status="Open")


class TestUpdateLeadNote(FrappeTestCase):
	def test_refuses_a_note_that_is_not_on_the_lead(self):
		from phamos.api import sales_leads

		doc = MagicMock()
		doc.notes = [SimpleNamespace(name="NOTE-1")]
		with (
			patch.object(sales_leads, "_check_lead_access"),
			patch("frappe.has_permission"),
			patch("frappe.get_doc", return_value=doc),
		):
			with self.assertRaises(frappe.ValidationError):
				sales_leads.update_lead_note("LEAD-1", "NOTE-OTHER", "text")
		doc.edit_note.assert_not_called()

	def test_refuses_an_empty_note(self):
		from phamos.api import sales_leads

		doc = MagicMock()
		doc.notes = [SimpleNamespace(name="NOTE-1")]
		with (
			patch.object(sales_leads, "_check_lead_access"),
			patch("frappe.has_permission"),
			patch("frappe.get_doc", return_value=doc),
		):
			with self.assertRaises(frappe.ValidationError):
				sales_leads.update_lead_note("LEAD-1", "NOTE-1", "   ")



class TestLeadDirection(FrappeTestCase):
	"""Inbound / Outbound on Lead (phamos/phamos#574): required on new leads, never blocking automatic ones."""

	def _lead(self, source=None, new=True, direction=None, **flags):
		doc = frappe.get_doc(
			{"doctype": "Lead", "first_name": "Direction", "source": source, "custom_lead_direction": direction}
		)
		# insert() marks a new document this way before before_validate runs.
		if new:
			doc.set("__islocal", 1)
		else:
			doc.name = "CRM-LEAD-EXISTING"
		for key, value in flags.items():
			doc.flags[key] = value
		return doc

	def _run(self, doc, source_direction=None, user="test@example.com"):
		from phamos.marketing import crm

		with (
			patch.object(crm, "lead_source_direction", return_value=source_direction),
			patch("frappe.session", SimpleNamespace(user=user)),
		):
			crm.lead_set_direction(doc)
		return doc.custom_lead_direction

	def test_a_chosen_value_is_kept(self):
		doc = self._lead(source="Cold Calling", direction="Inbound")
		self.assertEqual(self._run(doc, source_direction="Outbound"), "Inbound")

	def test_the_source_mapping_wins_over_the_fallback(self):
		doc = self._lead(source="Cold Calling", ignore_mandatory=True)
		self.assertEqual(self._run(doc, source_direction="Outbound", user="Guest"), "Outbound")

	def test_a_website_guest_lead_is_inbound(self):
		self.assertEqual(self._run(self._lead(), user="Guest"), "Inbound")

	def test_an_email_lead_is_inbound(self):
		"""frappe's email receive and ERPNext's "Make Lead" set ignore_mandatory."""
		self.assertEqual(self._run(self._lead(ignore_mandatory=True)), "Inbound")

	def test_a_creation_path_can_set_its_own_default(self):
		self.assertEqual(self._run(self._lead(lead_direction_default="Outbound")), "Outbound")

	def test_a_new_desk_lead_without_a_value_is_refused(self):
		with self.assertRaises(frappe.MandatoryError):
			self._run(self._lead())

	def test_an_existing_lead_without_a_value_still_saves(self):
		"""Old leads without a source: every later edit, the cockpit's autosave included, must still work."""
		doc = self._lead(new=False)
		self.assertFalse(self._run(doc))

	def test_create_lead_marks_website_and_event_leads_inbound(self):
		from phamos.marketing import crm

		inserted = []
		with patch("frappe.model.document.Document.insert", lambda self, **kw: inserted.append(self)):
			crm.create_lead(email="anna@example.com", first_name="Anna", source="Website")
		self.assertEqual(inserted[0].flags.lead_direction_default, "Inbound")

	def test_source_seeding_never_overwrites_a_value(self):
		from phamos.marketing import setup

		set_calls = []
		existing = {"Cold Calling": "Inbound"}  # changed by hand in Desk
		with (
			patch.object(setup, "create_custom_fields"),
			patch("frappe.db.exists", return_value=True),
			patch("frappe.db.get_value", side_effect=lambda dt, name, field: existing.get(name)),
			patch("frappe.db.set_value", side_effect=lambda *a, **kw: set_calls.append(a)),
		):
			setup.ensure_lead_direction()
		changed = {call[1] for call in set_calls}
		self.assertNotIn("Cold Calling", changed)
		self.assertIn("Website", changed)

	def test_choosing_a_source_in_the_cockpit_sets_its_direction(self):
		from phamos.api import sales_leads

		doc = MagicMock()
		doc.modified = "2026-11-12 10:00:00"
		doc.custom_status_comment = ""
		with (
			patch.object(sales_leads, "_check_lead_access"),
			patch("frappe.get_doc", return_value=doc),
			patch("phamos.marketing.crm.lead_source_direction", return_value="Outbound"),
			patch.object(sales_leads, "get_lead", return_value={}),
		):
			sales_leads.update_lead("LEAD-1", source="Cold Calling")
		set_fields = {c.args[0]: c.args[1] for c in doc.set.call_args_list}
		self.assertEqual(set_fields.get("custom_lead_direction"), "Outbound")
