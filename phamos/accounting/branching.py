# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Create the ERPNext documents a receipt branches into. Here: the Purchase Invoice.

Each item line becomes an invoice line without an Item: description, quantity, rate and
the line's expense account. A line without an expense account stops the invoice. The tax rate the AI read selects the Item Tax Template (0 / 7 / 19 %);
the header uses the company's default purchase tax template.
"""

import json

import frappe
from erpnext import get_default_company
from frappe import _
from frappe.utils import flt

from phamos.accounting.expense_accounts import item_tax_template_for_rate

TOTAL_TOLERANCE = 0.02


class LineWithoutAccount(frappe.ValidationError):
	pass


def make_purchase_invoice(receipt, submit=False):
	"""Draft (or submitted) Purchase Invoice from the receipt's lines. Returns the PI doc;
	`pi.flags.receipt_warnings` lists differences the human should look at."""
	if receipt.purchase_invoice and frappe.db.exists("Purchase Invoice", {"name": receipt.purchase_invoice, "docstatus": ("<", 2)}):
		frappe.throw(_("This receipt already has Purchase Invoice {0}.").format(receipt.purchase_invoice))
	if not receipt.supplier:
		frappe.throw(_("Set the supplier first."))
	if not receipt.get("items"):
		frappe.throw(_("The receipt has no item lines."))

	company = receipt.company or get_default_company()
	pi = frappe.new_doc("Purchase Invoice")
	pi.company = company
	pi.supplier = receipt.supplier
	pi.currency = receipt.currency
	pi.conversion_rate = receipt.conversion_rate or 1
	if receipt.posting_date:
		pi.set_posting_time = 1
		pi.posting_date = receipt.posting_date
		pi.bill_date = receipt.posting_date
	pi.bill_no = receipt.supplier_reference
	if receipt.due_date and not receipt.is_return:
		pi.due_date = receipt.due_date
	pi.cost_center = receipt.cost_center
	pi.project = receipt.project
	pi.remarks = f"{receipt.title} ({receipt.name})"
	if receipt.is_return:
		pi.is_return = 1
		if receipt.return_against:
			pi.return_against = frappe.db.get_value("Accounting Receipt", receipt.return_against, "purchase_invoice")

	missing = []
	for idx, line in enumerate(receipt.items, 1):
		account = line.expense_account
		if not account:
			missing.append(f"{idx}. {line.item_name}")
			continue
		qty, rate, description = _quantity(line)
		row = {
			"item_name": line.item_name,
			"description": description,
			"qty": -abs(qty) if receipt.is_return else qty,
			"rate": rate,
			"uom": "Nos",
			"conversion_factor": 1,
			"expense_account": account,
			"cost_center": line.cost_center or receipt.cost_center,
			"project": line.project or receipt.project,
		}
		template = item_tax_template_for_rate(line.tax_rate, company)
		if template:
			row["item_tax_template"] = template
			row["item_tax_rate"] = json.dumps(_template_rates(template))
		pi.append("items", row)

	if missing:
		frappe.throw(
			_("These lines need an expense account: {0}").format(", ".join(missing)),
			LineWithoutAccount,
		)

	pi.set_missing_values()
	# set_missing_values may fill defaults; the line's own account and text win.
	for row, line in zip(pi.items, receipt.items):
		row.expense_account = line.expense_account
		row.item_name = line.item_name
		row.description = _quantity(line)[2]
	if not pi.get("taxes"):
		pi.set_taxes()
	pi.calculate_taxes_and_totals()

	warnings = []
	if receipt.sum and abs(flt(pi.grand_total) - abs(flt(receipt.sum))) > TOTAL_TOLERANCE:
		warnings.append(
			_("Invoice total {0} differs from the receipt total {1}. Check taxes and lines.").format(
				frappe.format(pi.grand_total, {"fieldtype": "Currency", "options": pi.currency}),
				frappe.format(receipt.sum, {"fieldtype": "Currency", "options": receipt.currency}),
			)
		)
	pi.insert()
	_attach_pdf(receipt, pi)
	receipt.db_set("purchase_invoice", pi.name)
	if submit and not warnings:
		pi.submit()
	pi.flags.receipt_warnings = warnings
	return pi


def _quantity(line):
	"""(qty, rate, description) for the invoice line.

	Lines carry no unit, and the invoice uses "Nos", which only allows whole numbers.
	A fractional quantity (50.08 hours, 37.5 litres) therefore goes on the invoice as one
	unit at the line amount, with the original quantity and rate kept in the description.
	"""
	qty = abs(flt(line.qty)) or 1
	rate = flt(line.rate) or (flt(line.amount) / qty if qty else 0)
	if qty == int(qty):
		return qty, rate, line.item_name
	amount = flt(line.amount) or flt(qty * rate, 2)
	return 1, amount, f"{line.item_name} ({qty:g} × {rate:.2f})"


def _template_rates(template):
	rows = frappe.get_all("Item Tax Template Detail", filters={"parent": template}, fields=["tax_type", "tax_rate"])
	return {r.tax_type: flt(r.tax_rate) for r in rows}


def _attach_pdf(receipt, pi):
	if not receipt.attachment:
		return
	file_name = frappe.db.get_value("File", {"file_url": receipt.attachment}, "file_name") or receipt.attachment.rsplit("/", 1)[-1]
	frappe.get_doc(
		{
			"doctype": "File",
			"file_url": receipt.attachment,
			"file_name": file_name,
			"is_private": 1 if receipt.attachment.startswith("/private/") else 0,
			"attached_to_doctype": "Purchase Invoice",
			"attached_to_name": pi.name,
		}
	).insert(ignore_permissions=True)


# --- Payment Request ----------------------------------------------------------------------

OPEN_PAYMENT_REQUEST_STATUSES = ("Draft", "Initiated", "Requested")


def company_bank_accounts(company):
	"""The company's own bank accounts a receipt can be paid from."""
	return frappe.get_all(
		"Bank Account",
		filters={"is_company_account": 1, "company": company, "disabled": 0},
		fields=["name", "account_name", "bank", "account", "iban", "is_default"],
		order_by="is_default desc, account_name asc",
	)


def supplier_bank_account(supplier):
	"""The supplier's bank account ERPNext puts on the Payment Request (the creditor's IBAN)."""
	from erpnext.accounts.doctype.bank_account.bank_account import get_party_bank_account

	return get_party_bank_account("Supplier", supplier) if supplier else None


def make_payment_request(receipt, mode_of_payment=None, bank_account=None):
	"""Submitted outward Payment Request for the receipt's submitted Purchase Invoice.

	The paying company account and the due date are kept on the receipt and repeated in
	the request's subject and message, because a Payment Request has no fields for them.
	"""
	from erpnext.accounts.doctype.payment_request.payment_request import make_payment_request as erpnext_make

	from phamos.phamos.doctype.accounting_receipt.accounting_receipt import submitted_purchase_invoice

	pi_name = submitted_purchase_invoice(receipt)
	if not pi_name:
		frappe.throw(_("A Payment Request needs a submitted Purchase Invoice."))
	existing = open_payment_request(receipt)
	if existing:
		frappe.throw(_("This receipt already has Payment Request {0}.").format(existing))
	pi = frappe.get_doc("Purchase Invoice", pi_name)
	if flt(pi.outstanding_amount) <= 0:
		frappe.throw(_("Purchase Invoice {0} has nothing left to pay.").format(pi.name))

	pr = erpnext_make(
		dt="Purchase Invoice",
		dn=pi.name,
		party_type="Supplier",
		party=pi.supplier,
		party_name=pi.supplier_name,
		mode_of_payment=mode_of_payment,
		mute_email=1,
		submit_doc=1,
		return_doc=1,
	)
	pay_from = frappe.db.get_value("Bank Account", bank_account, ["account_name", "iban"], as_dict=True) if bank_account else None
	due = frappe.format(receipt.due_date, {"fieldtype": "Date"}) if receipt.due_date else _("no due date")
	subject = _("Pay {0} {1} by {2}").format(pi.supplier_name, receipt.supplier_reference or pi.name, due)
	lines = [
		subject,
		_("Receipt: {0}").format(receipt.name),
		_("Purchase Invoice: {0}").format(pi.name),
	]
	if pay_from:
		lines.append(_("Pay from: {0} {1}").format(pay_from.account_name, pay_from.iban or ""))
	if receipt.payment_reference:
		lines.append(_("Payment reference: {0}").format(receipt.payment_reference))
	pr.db_set({"subject": subject[:140], "message": "\n".join(lines)}, update_modified=False)
	receipt.db_set("payment_request", pr.name)
	return pr


def open_payment_request(receipt):
	"""The receipt's Payment Request while it is still open (not paid, not cancelled)."""
	name = receipt.get("payment_request")
	if name and frappe.db.get_value("Payment Request", name, "status") in OPEN_PAYMENT_REQUEST_STATUSES:
		return name
	return None


def cancel_payment_request(receipt):
	"""Cancel the receipt's open Payment Request (when it is not paid after all). Returns its name."""
	name = open_payment_request(receipt)
	if not name:
		return None
	pr = frappe.get_doc("Payment Request", name)
	pr.flags.ignore_permissions = True
	if pr.docstatus == 1:
		pr.cancel()
	elif pr.docstatus == 0:
		pr.delete(ignore_permissions=True)
		receipt.db_set("payment_request", None)
	return name
