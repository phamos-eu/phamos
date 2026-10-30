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


class TestCleanAttachments(FrappeTestCase):
	"""Only files that belong to this lead may ride along on its mail."""

	def test_scopes_file_names_to_the_lead(self):
		from phamos.api.sales_leads import _clean_attachments

		with patch("frappe.get_all", return_value=["FILE-mine"]) as get_all:
			kept = _clean_attachments("LEAD-1", ["FILE-mine", "FILE-someone-elses"])

		self.assertEqual(kept, ["FILE-mine"])
		_, kwargs = get_all.call_args
		filters = kwargs["filters"]
		self.assertEqual(filters["attached_to_doctype"], "Lead")
		self.assertEqual(filters["attached_to_name"], "LEAD-1")
		self.assertCountEqual(filters["name"][1], ["FILE-mine", "FILE-someone-elses"])

	def test_no_attachments_asks_nothing(self):
		from phamos.api.sales_leads import _clean_attachments

		with patch("frappe.get_all") as get_all:
			self.assertEqual(_clean_attachments("LEAD-1", None), [])
			get_all.assert_not_called()

	def test_accepts_a_json_string(self):
		from phamos.api.sales_leads import _clean_attachments

		with patch("frappe.get_all", return_value=[]), patch(
			"frappe.parse_json", return_value=["FILE-1"]
		) as parse:
			_clean_attachments("LEAD-1", '["FILE-1"]')
			parse.assert_called_once()


class TestNextStepSorting(FrappeTestCase):
	"""The checklist reads chronologically; undated steps sit last."""

	def test_dated_before_undated(self):
		from phamos.api.sales_leads import _next_step_sort_key

		# The rows come from a child table, so they are dict-like, not attributes.
		rows = [
			{"next_step": "later", "date": "2026-03-01"},
			{"next_step": "no date", "date": None},
			{"next_step": "sooner", "date": "2026-01-01"},
		]
		ordered = [r["next_step"] for r in sorted(rows, key=_next_step_sort_key)]
		self.assertEqual(ordered, ["sooner", "later", "no date"])
