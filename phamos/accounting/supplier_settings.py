# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Per-supplier settings for the AI Accountant (custom fields on Supplier, tab "AI Accountant").

They override the skills' general settings for one supplier. Empty means: use the general setting.
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, cstr, flt

FIELDS = {
	"custom_ai_always_review": "always_review",
	"custom_ai_auto_datev": "auto_datev",
	"custom_ai_amount_tolerance_pct": "amount_tolerance_pct",
	"custom_ai_payment_mode": "payment_mode",
	"custom_ai_expense_account": "expense_account",
	"custom_ai_cost_center": "cost_center",
}
PAID_MODES = ("Direct Debit", "Credit Card", "PayPal")


def ensure_fields():
	if frappe.get_meta("Supplier").has_field("custom_ai_payment_mode"):
		return
	create_custom_fields(
		{
			"Supplier": [
				{"fieldname": "custom_ai_tab", "fieldtype": "Tab Break", "label": "AI Accountant", "insert_after": "column_break_1mqv",
					"module": "Phamos"},
				{"fieldname": "custom_ai_always_review", "fieldtype": "Check", "label": "Always needs a person",
					"insert_after": "custom_ai_tab", "module": "Phamos",
					"description": "The AI never marks this supplier's receipts as ready on its own."},
				{"fieldname": "custom_ai_auto_datev", "fieldtype": "Select", "label": "Send to DATEV automatically",
					"options": "Default\nAllow\nNever", "default": "Default", "insert_after": "custom_ai_always_review", "module": "Phamos",
					"description": "Default follows the AI skill. Allow sends paid, clear receipts of this supplier automatically. Never never does."},
				{"fieldname": "custom_ai_amount_tolerance_pct", "fieldtype": "Percent", "label": "Usual amount ± (%)",
					"insert_after": "custom_ai_auto_datev", "module": "Phamos",
					"description": "How far an amount may be from this supplier's usual one. Empty: the AI skill's setting."},
				{"fieldname": "custom_ai_column", "fieldtype": "Column Break", "insert_after": "custom_ai_amount_tolerance_pct",
					"module": "Phamos"},
				{"fieldname": "custom_ai_payment_mode", "fieldtype": "Select", "label": "Paid by",
					"options": "\nBank Transfer\nDirect Debit\nCredit Card\nPayPal", "insert_after": "custom_ai_column", "module": "Phamos",
					"description": "Direct debit, card or PayPal: receipts are already paid; nothing to approve."},
				{"fieldname": "custom_ai_expense_account", "fieldtype": "Link", "label": "Default Expense Account",
					"options": "Account", "insert_after": "custom_ai_payment_mode", "module": "Phamos",
					"description": "For lines the assignment library has no answer for (before Mistral is asked)."},
				{"fieldname": "custom_ai_cost_center", "fieldtype": "Link", "label": "Default Cost Center",
					"options": "Cost Center", "insert_after": "custom_ai_expense_account", "module": "Phamos"},
			]
		},
		update=False,
	)


def get(supplier):
	"""The supplier's AI settings as a dict (empty values left out)."""
	if not supplier or not frappe.get_meta("Supplier").has_field("custom_ai_payment_mode"):
		return {}
	row = frappe.db.get_value("Supplier", supplier, list(FIELDS), as_dict=True) or {}
	result = {}
	for field, key in FIELDS.items():
		value = row.get(field)
		if key == "always_review":
			if cint(value):
				result[key] = 1
		elif key == "auto_datev":
			if value and value != "Default":
				result[key] = value
		elif key == "amount_tolerance_pct":
			if value not in (None, "") and flt(value) > 0:
				result[key] = flt(value)
		elif value:
			result[key] = value
	return result


def is_paid_by_mode(settings):
	return settings.get("payment_mode") in PAID_MODES


@frappe.whitelist(methods=["POST"])
def list_settings():
	"""Suppliers that have any AI setting."""
	frappe.has_permission("Supplier", "read", throw=True)
	ensure_fields()
	rows = frappe.get_all(
		"Supplier",
		or_filters={"custom_ai_always_review": 1, "custom_ai_auto_datev": ("in", ("Allow", "Never")),
			"custom_ai_amount_tolerance_pct": (">", 0), "custom_ai_payment_mode": ("is", "set"),
			"custom_ai_expense_account": ("is", "set"), "custom_ai_cost_center": ("is", "set")},
		fields=["name", "supplier_name"] + list(FIELDS),
		order_by="supplier_name asc",
		limit_page_length=500,
	)
	return [{"supplier": r.name, "supplier_name": r.supplier_name, **get(r.name)} for r in rows]


@frappe.whitelist(methods=["POST"])
def get_settings(supplier):
	doc = frappe.get_doc("Supplier", supplier)
	doc.check_permission("read")
	ensure_fields()
	values = {key: doc.get(field) for field, key in FIELDS.items()}
	values["amount_tolerance_pct"] = values["amount_tolerance_pct"] or None  # an empty Percent reads as 0
	values["auto_datev"] = values["auto_datev"] or "Default"
	return {"supplier": doc.name, "supplier_name": doc.supplier_name, "can_write": 1 if doc.has_permission("write") else 0, **values}


@frappe.whitelist(methods=["POST"])
def save_settings(supplier, values):
	values = frappe.parse_json(values) if isinstance(values, str) else values or {}
	doc = frappe.get_doc("Supplier", supplier)
	doc.check_permission("write")
	ensure_fields()
	for field, key in FIELDS.items():
		if key in values:
			value = values[key]
			if key == "always_review":
				value = 1 if cint(value) else 0
			elif key == "auto_datev":
				value = value if value in ("Default", "Allow", "Never") else "Default"
			elif key == "amount_tolerance_pct":
				value = flt(value) if value not in (None, "") else None
			else:
				value = cstr(value).strip() or None
			doc.set(field, value)
	if doc.get("custom_ai_expense_account"):
		root, is_group = frappe.db.get_value("Account", doc.custom_ai_expense_account, ["root_type", "is_group"]) or (None, None)
		if root != "Expense" or is_group:
			frappe.throw(_("{0} is not an expense account.").format(doc.custom_ai_expense_account))
	doc.save()
	return get_settings(supplier)
