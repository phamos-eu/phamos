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
	for field, doctype in (("expense_claim", "Expense Claim"), ("journal_entry", "Journal Entry")):
		if receipt.get(field) and frappe.db.exists(doctype, {"name": receipt.get(field), "docstatus": ("<", 2)}):
			frappe.throw(_("This receipt is already booked as {0} {1}.").format(_(doctype), receipt.get(field)))
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


# --- Net amounts and input VAT ------------------------------------------------------------


class NoInputVatAccount(frappe.ValidationError):
	pass


def input_vat_account(rate, company):
	"""Input VAT (Vorsteuer) account for a tax rate: the matching row of the company's default
	purchase tax template, else any tax asset account with that rate."""
	if not flt(rate):
		return None
	template = frappe.db.get_value("Purchase Taxes and Charges Template", {"company": company, "is_default": 1, "disabled": 0}, "name")
	if template:
		heads = frappe.get_all("Purchase Taxes and Charges", filters={"parent": template}, pluck="account_head")
		for head in heads:
			if abs(flt(frappe.db.get_value("Account", head, "tax_rate")) - flt(rate)) < 0.01:
				return head
	return frappe.db.get_value(
		"Account",
		{"company": company, "account_type": "Tax", "root_type": "Asset", "is_group": 0, "disabled": 0, "tax_rate": flt(rate)},
		"name",
		order_by="name asc",
	)


def net_lines_and_taxes(receipt, company):
	"""Split the receipt lines into net expense amounts and input VAT per rate.

	Lines may hold net or gross amounts (that depends on the invoice); whichever total the
	lines match (net_total or sum) decides. Returns {"lines": [...], "taxes": [...], "total"}
	where total is the gross amount, rounded so net + VAT equals the receipt total."""
	lines = receipt.get("items") or []
	if not lines:
		frappe.throw(_("The receipt has no item lines."))
	missing = [f"{i}. {line.item_name}" for i, line in enumerate(lines, 1) if not line.expense_account]
	if missing:
		frappe.throw(_("These lines need an expense account: {0}").format(", ".join(missing)), LineWithoutAccount)

	line_total = sum(flt(line.amount) for line in lines)
	gross = flt(receipt.sum)
	net_total = flt(receipt.net_total)
	if net_total and abs(line_total - net_total) <= 0.05:
		lines_are_gross = False
	elif gross and abs(line_total - gross) <= 0.05:
		lines_are_gross = True
	else:
		lines_are_gross = not flt(receipt.total_taxes)

	rows, tax_by_rate = [], {}
	for line in lines:
		rate = flt(line.tax_rate)
		amount = flt(line.amount)
		net = amount / (1 + rate / 100) if lines_are_gross and rate else amount
		tax = amount - net if lines_are_gross else net * rate / 100
		rows.append({
			"description": line.item_name,
			"account": line.expense_account,
			"net": flt(net, 2),
			"rate": rate,
			"cost_center": line.cost_center or receipt.cost_center,
			"project": line.project or receipt.project,
		})
		if rate:
			tax_by_rate[rate] = tax_by_rate.get(rate, 0) + tax

	taxes = []
	for rate, amount in sorted(tax_by_rate.items()):
		account = input_vat_account(rate, company)
		if not account:
			frappe.throw(_("No input VAT account for {0} % in {1}.").format(rate, company), NoInputVatAccount)
		taxes.append({"rate": rate, "account": account, "amount": flt(amount, 2)})

	total = flt(sum(r["net"] for r in rows) + sum(t["amount"] for t in taxes), 2)
	difference = flt(gross - total, 2) if gross else 0
	if difference and abs(difference) <= 0.05:  # rounding: put the cents on the largest amount
		target = max(taxes, key=lambda t: t["amount"]) if taxes else max(rows, key=lambda r: r["net"])
		target["amount" if taxes else "net"] = flt(target["amount" if taxes else "net"] + difference, 2)
		total = gross
	return {"lines": rows, "taxes": taxes, "total": total, "lines_are_gross": lines_are_gross}


def _attach_pdf_to(receipt, doctype, name):
	if not receipt.attachment:
		return
	file_name = frappe.db.get_value("File", {"file_url": receipt.attachment}, "file_name") or receipt.attachment.rsplit("/", 1)[-1]
	frappe.get_doc(
		{
			"doctype": "File",
			"file_url": receipt.attachment,
			"file_name": file_name,
			"is_private": 1 if receipt.attachment.startswith("/private/") else 0,
			"attached_to_doctype": doctype,
			"attached_to_name": name,
		}
	).insert(ignore_permissions=True)


def _check_no_other_booking(receipt):
	for field, doctype in (("purchase_invoice", "Purchase Invoice"), ("expense_claim", "Expense Claim"), ("journal_entry", "Journal Entry")):
		name = receipt.get(field)
		if name and frappe.db.exists(doctype, {"name": name, "docstatus": ("<", 2)}):
			frappe.throw(_("This receipt is already booked as {0} {1}.").format(_(doctype), name))


# --- Expense Claim ------------------------------------------------------------------------


def employee_for(receipt):
	"""The employee who paid: set on the receipt, else the one whose user uploaded it."""
	if receipt.get("employee"):
		return receipt.employee
	if receipt.uploaded_by:
		return frappe.db.get_value("Employee", {"user_id": receipt.uploaded_by, "status": "Active"}, "name")
	return None


def expense_type_for(account, company, fallback=None):
	"""The Expense Claim Type booked on this account for the company, else the fallback."""
	rows = frappe.get_all("Expense Claim Account", filters={"company": company, "default_account": account,
		"parenttype": "Expense Claim Type"}, pluck="parent")
	return rows[0] if rows else fallback


def default_expense_type():
	return "Others" if frappe.db.exists("Expense Claim Type", "Others") else frappe.db.get_value("Expense Claim Type", {}, "name")


def make_expense_claim(receipt, employee=None, expense_type=None):
	"""Draft Expense Claim reimbursing the employee who paid the receipt privately.

	One expense row per line at its net amount, booked on the line's expense account, and
	the input VAT as tax rows. The AI never submits it; approval stays with the approver."""
	_check_no_other_booking(receipt)
	company = receipt.company or get_default_company()
	employee = employee or employee_for(receipt)
	if not employee:
		frappe.throw(_("Choose the employee who paid."))
	split = net_lines_and_taxes(receipt, company)
	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	if receipt.currency and receipt.currency != company_currency:
		frappe.throw(_("Expense Claims are in {0}; this receipt is in {1}.").format(company_currency, receipt.currency))

	fallback = expense_type or default_expense_type()
	if not fallback:
		frappe.throw(_("Create an Expense Claim Type first (HR > Expense Claim Type)."))
	posting_date = receipt.posting_date or frappe.utils.today()
	claim = frappe.new_doc("Expense Claim")
	claim.update(
		{
			"employee": employee,
			"company": company,
			"posting_date": posting_date,
			"expense_approver": frappe.db.get_value("Employee", employee, "expense_approver"),
			"payable_account": frappe.get_cached_value("Company", company, "default_expense_claim_payable_account"),
			"cost_center": receipt.cost_center,
			"project": receipt.project,
			"remark": f"{receipt.title} ({receipt.name})",
		}
	)
	for row in split["lines"]:
		claim.append(
			"expenses",
			{
				"expense_date": posting_date,
				"expense_type": expense_type_for(row["account"], company, fallback),
				"default_account": row["account"],
				"description": row["description"],
				"amount": row["net"],
				"sanctioned_amount": row["net"],
				"cost_center": row["cost_center"],
				"project": row["project"],
			},
		)
	for tax in split["taxes"]:
		claim.append(
			"taxes",
			{
				"account_head": tax["account"],
				"description": _("Input VAT {0} %").format(tax["rate"]),
				"rate": 0,
				"tax_amount": tax["amount"],
				"cost_center": receipt.cost_center,
			},
		)
	claim.insert()
	_attach_pdf_to(receipt, "Expense Claim", claim.name)
	receipt.db_set({"expense_claim": claim.name, "employee": employee})
	warnings = []
	if not claim.payable_account:
		warnings.append(_("The company has no default expense claim payable account; set it before submitting."))
	if not claim.expense_approver:
		warnings.append(_("The employee has no expense approver."))
	claim.flags.receipt_warnings = warnings
	return claim


# --- Journal Entry ------------------------------------------------------------------------


def make_journal_entry(receipt, credit_account):
	"""Draft Journal Entry for a receipt without a supplier invoice (tax notice, bank fees,
	card statement): debit the lines' expense accounts (net) and input VAT, credit the
	account it was paid from or is owed on. The AI never submits it."""
	_check_no_other_booking(receipt)
	company = receipt.company or get_default_company()
	if not credit_account:
		frappe.throw(_("Choose the account to credit (the bank it was paid from, or what is owed)."))
	credit = frappe.db.get_value("Account", credit_account, ["company", "is_group", "account_type", "disabled"], as_dict=True)
	if not credit or credit.company != company or credit.is_group or credit.disabled:
		frappe.throw(_("{0} is not a ledger account of {1}.").format(credit_account, company))
	if credit.account_type in ("Payable", "Receivable"):
		frappe.throw(_("{0} needs a party; use a Purchase Invoice for supplier invoices.").format(credit_account))
	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	if receipt.currency and receipt.currency != company_currency:
		frappe.throw(_("Journal Entries from receipts are in {0} only; this receipt is in {1}.").format(company_currency, receipt.currency))
	split = net_lines_and_taxes(receipt, company)
	is_bank = credit.account_type in ("Bank", "Cash")
	posting_date = receipt.posting_date or frappe.utils.today()
	je = frappe.new_doc("Journal Entry")
	je.update(
		{
			"voucher_type": "Bank Entry" if credit.account_type == "Bank" else ("Cash Entry" if credit.account_type == "Cash" else "Journal Entry"),
			"company": company,
			"posting_date": posting_date,
			"cheque_no": receipt.supplier_reference or receipt.name,
			"cheque_date": posting_date,
			"user_remark": f"{receipt.title} ({receipt.name})",
		}
	)
	if not is_bank:
		je.cheque_no = receipt.supplier_reference
	for row in split["lines"]:
		je.append("accounts", {"account": row["account"], "debit_in_account_currency": row["net"],
			"cost_center": row["cost_center"], "project": row["project"], "user_remark": row["description"]})
	for tax in split["taxes"]:
		je.append("accounts", {"account": tax["account"], "debit_in_account_currency": tax["amount"],
			"user_remark": _("Input VAT {0} %").format(tax["rate"])})
	je.append("accounts", {"account": credit_account, "credit_in_account_currency": split["total"],
		"cost_center": receipt.cost_center})
	je.insert()
	_attach_pdf_to(receipt, "Journal Entry", je.name)
	receipt.db_set("journal_entry", je.name)
	je.flags.receipt_warnings = []
	return je
