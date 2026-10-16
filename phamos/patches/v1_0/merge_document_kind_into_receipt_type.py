"""Document Kind and Receipt Type described the same thing; Receipt Type is the one field now.

Receipt Type takes the descriptive values (Invoice, Credit Note, Receipt, Tax Notice,
Contract, Reminder, Statement, Other). A value the AI already read as document kind wins;
otherwise the old Receipt Type is mapped: Purchase Invoice → Invoice, Sonstiges → Other,
Journal Entry / Payment → Receipt. DATEV recipient rows are remapped the same way, so the
upload addresses keep receiving the same documents. Safe to run twice.
"""

import frappe

DOCTYPE = "Accounting Receipt"
NEW_TYPES = ("Invoice", "Credit Note", "Receipt", "Tax Notice", "Contract", "Reminder", "Statement", "Other")
OLD_TO_NEW = {"purchase invoice": "Invoice", "sonstiges": "Other", "journal entry": "Receipt", "payment": "Receipt"}
INVOICE_ADDRESS_TYPES = "Invoice, Credit Note, Receipt"
OTHER_ADDRESS_TYPES = "Tax Notice, Contract, Reminder, Statement, Other"


def execute():
	has_kind = frappe.db.has_column(DOCTYPE, "document_kind")
	fields = "name, receipt_type" + (", document_kind" if has_kind else "")
	for row in frappe.db.sql(f"select {fields} from `tab{DOCTYPE}`", as_dict=True):
		new = new_receipt_type(row.get("receipt_type"), row.get("document_kind"))
		if new != (row.receipt_type or ""):
			frappe.db.set_value(DOCTYPE, row.name, "receipt_type", new or None, update_modified=False)
	_remap_datev_recipients()


def new_receipt_type(receipt_type, document_kind=None):
	if document_kind in NEW_TYPES:
		return document_kind
	if receipt_type in NEW_TYPES:
		return receipt_type
	return OLD_TO_NEW.get((receipt_type or "").strip().lower(), "Other" if receipt_type else "")


def _remap_datev_recipients():
	for row in frappe.get_all("DATEV Recipient", fields=["name", "receipt_types", "is_default"]):
		old = [t.strip().lower() for t in (row.receipt_types or "").split(",") if t.strip()]
		if any(t in ("purchase invoice", "journal entry", "payment") for t in old):
			frappe.db.set_value("DATEV Recipient", row.name, "receipt_types", INVOICE_ADDRESS_TYPES)
		elif "sonstiges" in old:
			frappe.db.set_value("DATEV Recipient", row.name, "receipt_types", OTHER_ADDRESS_TYPES)
