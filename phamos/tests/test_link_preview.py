# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for the FrappeLink dropdown preview-lines API."""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.link_preview import get_link_preview_lines


def _field(fieldname, fieldtype="Data", in_preview=0, label=None):
	return SimpleNamespace(
		fieldname=fieldname, fieldtype=fieldtype, in_preview=in_preview, label=label or fieldname
	)


class _FakeMeta:
	"""Minimal stand-in for frappe.get_meta(doctype)."""

	def __init__(self, fields, search_fields):
		self.fields = fields
		self._search_fields = search_fields
		self._by_fieldname = {f.fieldname: f for f in fields}

	def get_search_fields(self):
		return self._search_fields

	def get_field(self, fieldname):
		return self._by_fieldname.get(fieldname)


class TestGetLinkPreviewLines(FrappeTestCase):
	def test_empty_names_returns_empty_without_touching_db(self):
		with (
			patch("frappe.get_meta") as get_meta,
			patch("frappe.get_list") as get_list,
		):
			self.assertEqual(get_link_preview_lines("Contact", []), {})
			self.assertEqual(get_link_preview_lines("", ["C-0001"]), {})
			get_meta.assert_not_called()
			get_list.assert_not_called()

	def test_no_search_or_preview_fields_skips_the_query(self):
		"""Only get_search_fields()'s own "name" entry is configured — that's
		filtered out (it's already the option's value/label) — so there's
		nothing worth fetching."""
		meta = _FakeMeta(fields=[], search_fields=["name"])
		with (
			patch("frappe.get_meta", return_value=meta),
			patch("frappe.get_list") as get_list,
		):
			result = get_link_preview_lines("Contact", ["C-0001"])
		self.assertEqual(result, {})
		get_list.assert_not_called()

	def test_parses_names_from_json_string(self):
		"""frappe-ui's call() serializes list params as a JSON string."""
		fields = [_field("email_id", in_preview=1, label="Email")]
		meta = _FakeMeta(fields=fields, search_fields=["name"])
		with (
			patch("frappe.get_meta", return_value=meta),
			patch("frappe.get_list", return_value=[]) as get_list,
		):
			get_link_preview_lines("Contact", '["C-0001", "C-0002"]')

		_, kwargs = get_list.call_args
		self.assertEqual(kwargs["filters"], {"name": ["in", ["C-0001", "C-0002"]]})

	def test_dedups_search_and_preview_fields_and_labels_values(self):
		fields = [
			_field("email_id", in_preview=1, label="Email"),
			_field("status", in_preview=0, label="Status"),
		]
		meta = _FakeMeta(fields=fields, search_fields=["name", "email_id"])
		rows = [frappe._dict(name="C-0001", email_id="a@example.com")]
		with (
			patch("frappe.get_meta", return_value=meta),
			patch("frappe.get_list", return_value=rows) as get_list,
			patch("frappe.format", side_effect=lambda value, field, translated=True: value),
		):
			result = get_link_preview_lines("Contact", ["C-0001"])

		args, kwargs = get_list.call_args
		self.assertEqual(args[0], "Contact")
		self.assertEqual(kwargs["fields"], ["name", "email_id"])
		self.assertEqual(result, {"C-0001": [{"label": "Email", "value": "a@example.com"}]})

	def test_omits_records_the_caller_cannot_read(self):
		"""frappe.get_list applies row-level permissions; a name filtered out
		by that (or simply gone) is just missing from the result, not an
		error — the caller already learned about it from a permitted
		search."""
		fields = [_field("email_id", in_preview=1, label="Email")]
		meta = _FakeMeta(fields=fields, search_fields=["name"])
		rows = [frappe._dict(name="C-0001", email_id="a@example.com")]
		with (
			patch("frappe.get_meta", return_value=meta),
			patch("frappe.get_list", return_value=rows),
			patch("frappe.format", side_effect=lambda value, field, translated=True: value),
		):
			result = get_link_preview_lines("Contact", ["C-0001", "C-0002"])

		self.assertIn("C-0001", result)
		self.assertNotIn("C-0002", result)

	def test_skips_blank_values(self):
		fields = [_field("email_id", in_preview=1, label="Email")]
		meta = _FakeMeta(fields=fields, search_fields=["name"])
		rows = [frappe._dict(name="C-0001", email_id="")]
		with (
			patch("frappe.get_meta", return_value=meta),
			patch("frappe.get_list", return_value=rows),
		):
			result = get_link_preview_lines("Contact", ["C-0001"])
		self.assertEqual(result, {})
