# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Contracts in the General Management Cockpit (#2147, slice #2148).

Built on ERPNext's standard Contract. This adds the "Contract Type" link on Contract and the first
two types. Called from after_migrate; idempotent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

SECTION = "custom_implementation_specific"
TYPE_FIELD = "custom_contract_type"
# Set once the first types were seeded, so deleting all of them later does not bring them back.
SEEDED_DEFAULT = "phamos_contract_types_seeded"
DEFAULT_TYPES = (
	("AVV", "Auftragsverarbeitungsvertrag (data processing agreement, Art. 28 GDPR)"),
	("NDA", "Non-disclosure agreement"),
)

CONTRACT_FIELDS = [
	{
		"fieldname": SECTION,
		"label": "Implementation Specific",
		"fieldtype": "Section Break",
		"insert_after": "",
		"collapsible": 0,
	},
	{
		"fieldname": TYPE_FIELD,
		"label": "Contract Type",
		"fieldtype": "Link",
		"options": "Contract Type",
		"insert_after": SECTION,
		"in_list_view": 1,
		"in_standard_filter": 1,
	},
]


def after_migrate():
	ensure_contract_fields()
	ensure_default_types()


def ensure_contract_fields():
	if not frappe.db.exists("DocType", "Contract"):
		return
	create_custom_fields({"Contract": CONTRACT_FIELDS}, update=True)


def ensure_default_types():
	"""Create the first types once. A type renamed or deleted later is left alone, even the last one.

	A site that already has types (made by hand, or seeded before the flag existed) is only marked.
	"""
	if frappe.db.get_default(SEEDED_DEFAULT):
		return
	if not frappe.db.count("Contract Type"):
		for name, description in DEFAULT_TYPES:
			frappe.get_doc(
				{"doctype": "Contract Type", "contract_type_name": name, "description": description}
			).insert(ignore_permissions=True)
	frappe.db.set_default(SEEDED_DEFAULT, 1)
