# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from frappe import _


def get_data():
	# delivery_note on this doc points to Delivery Note — internal link (not a field on DN).
	# fieldname + non_standard_fieldnames: safe fallback when no DN is set (query yields 0 rows).
	return {
		"fieldname": "name",
		"non_standard_fieldnames": {"Delivery Note": "name"},
		"internal_links": {"Delivery Note": "delivery_note"},
		"transactions": [{"label": _("Related"), "items": ["Delivery Note"]}],
	}
