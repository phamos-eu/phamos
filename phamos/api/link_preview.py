# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Labelled preview details for Link/Autocomplete dropdown options.

Used by the shared FrappeLink.vue component so users can tell records apart
in a search dropdown (e.g. picking a Contact) instead of just seeing a name.
Combines each DocType's configured Search Fields with every field marked
"Show in Preview" (the same fields Frappe's own document-preview popover
uses), and — unlike that raw value list — labels each one.
"""

import frappe
from frappe.model import no_value_fields, table_fields
from frappe.utils import cstr


def _preview_fieldnames(meta):
	fieldnames = [
		field.fieldname
		for field in meta.fields
		if field.in_preview
		and field.fieldtype not in no_value_fields
		and field.fieldtype not in table_fields
	]
	if fieldnames:
		return fieldnames
	# Nothing explicitly marked "Show in Preview" — fall back to mandatory
	# fields, same as Frappe's own document-preview popover (link_preview.py).
	return [field.fieldname for field in meta.fields if field.reqd and field.fieldtype not in table_fields]


def _search_fieldnames(meta):
	# get_search_fields() always appends "name"; that's already the option's
	# own value/label, so it isn't worth repeating as a preview line.
	return [fieldname for fieldname in meta.get_search_fields() if fieldname != "name"]


def _preview_line(value, meta, fieldname):
	if value in (None, ""):
		return None
	field = meta.get_field(fieldname)
	if not field:
		return {"label": fieldname, "value": cstr(value)}
	return {"label": field.label, "value": frappe.format(value, field, translated=True)}


@frappe.whitelist()
def get_link_preview_lines(doctype, names):
	"""Labelled preview lines (Search Fields + Show in Preview fields) per record.

	Returns {name: [{label, value}, ...]}. This only enriches records the
	caller already learned about from a permitted search, so records that no
	longer exist (or that get_list's permission checks filter out) are simply
	omitted rather than raising.
	"""
	names = frappe.parse_json(names) if isinstance(names, str) else (names or [])
	names = [cstr(name) for name in names if cstr(name).strip()]
	if not doctype or not names:
		return {}

	meta = frappe.get_meta(doctype)
	fieldnames = []
	for fieldname in [*_search_fieldnames(meta), *_preview_fieldnames(meta)]:
		if fieldname not in fieldnames:
			fieldnames.append(fieldname)
	if not fieldnames:
		return {}

	rows = frappe.get_list(
		doctype,
		filters={"name": ["in", names]},
		fields=["name", *fieldnames],
		limit_page_length=len(names),
	)

	result = {}
	for row in rows:
		lines = []
		for fieldname in fieldnames:
			line = _preview_line(row.get(fieldname), meta, fieldname)
			if line:
				lines.append(line)
		if lines:
			result[row.name] = lines
	return result
