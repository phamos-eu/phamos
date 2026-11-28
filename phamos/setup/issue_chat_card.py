# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The card at the top of an Issue chat (#2234).

Raven renders a record chat's link message as a card that lists the record's "In Preview" fields
(`raven.api.document_link.get_preview_data`). Issue has none in ERPNext, so the card showed only the
subject. These Property Setters mark the fields people need at a glance; Raven itself stays unchanged.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

PREVIEW_FIELDS = ("status", "priority", "issue_type", "customer", "custom_implementation", "project", "raised_by")


def after_migrate():
	meta = frappe.get_meta("Issue")
	changed = False
	for fieldname in PREVIEW_FIELDS:
		field = meta.get_field(fieldname)
		if not field or field.in_preview:
			continue
		make_property_setter("Issue", fieldname, "in_preview", 1, "Check", validate_fields_for_doctype=False)
		changed = True
	if changed:
		frappe.clear_cache(doctype="Issue")
