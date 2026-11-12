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


class TestGetLeads(FrappeTestCase):
	def test_undated_leads_sort_first(self):
		"""Leads with no follow-up date need triage, so they lead the list."""
		from phamos.api import sales_leads

		with (
			patch.object(sales_leads, "_check_lead_access"),
			patch("frappe.get_all", return_value=[]) as get_all,
		):
			sales_leads.get_leads()

		_, kwargs = get_all.call_args
		self.assertEqual(
			kwargs["order_by"], "custom_next_followup is null desc, custom_next_followup asc"
		)
		self.assertEqual(kwargs["filters"], {"disabled": 0})

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

