# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Accounts Receivable for the Accounting Cockpit (#1777).

`get_receivables` runs ERPNext's Accounts Receivable report for one company and adds what a
follow-up needs: whom to contact and when the customer was last reminded. Queries are small
helpers returning plain rows; `build_receivables` assembles them with the pure rules in
`phamos.accounting.receivables`, so tests patch the queries.

The report is called directly (as ERPNext's Process Statement of Accounts does), which skips
the checks Desk runs around a report. `_check_permission` and `_report_rows` apply them here, so
the cockpit shows a user exactly what the Desk report would.
"""

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, today

from phamos.accounting import receivables as rc
from phamos.api.accounting_stats import _resolve_company

AR_REPORT = "Accounts Receivable"
REPORT_REF_DOCTYPE = "Sales Invoice"
INVOICE_FIELDS = (
	"name",
	"contact_person",
	"contact_display",
	"contact_email",
	"contact_mobile",
	"status",
	"po_no",
	"currency",
	"outstanding_amount",
)


def can_read_receivables():
	"""Same gate as Desk's report: Report roles, not disabled, Sales Invoice report permission."""
	if not frappe.has_permission(REPORT_REF_DOCTYPE, "report"):
		return False
	if not frappe.db.exists("Report", AR_REPORT):
		return False
	report = frappe.get_doc("Report", AR_REPORT)
	return bool(not report.disabled and report.is_permitted())


def _check_permission():
	if not can_read_receivables():
		frappe.throw(_("Not permitted"), frappe.PermissionError)


# --- queries -------------------------------------------------------------------------


def _readable_companies():
	return frappe.get_list("Company", pluck="name", order_by="name asc")


def _report_rows(company, report_date):
	"""Open receivable rows of ERPNext's report, filtered by the user's permissions like Desk."""
	from erpnext.accounts.report.accounts_receivable.accounts_receivable import execute
	from frappe.desk.query_report import get_filtered_data

	columns, rows, *_ = execute({"company": company, "report_date": report_date, "ageing_based_on": "Due Date"})
	rows = get_filtered_data(REPORT_REF_DOCTYPE, columns, rows, frappe.session.user)
	return [row for row in rows if row.get("party_type") == "Customer" and row.get("voucher_no")]


def _invoice_details(names):
	"""Sales Invoice contact, status, PO and document currency per invoice name."""
	if not names:
		return {}
	rows = frappe.get_all(REPORT_REF_DOCTYPE, filters={"name": ("in", list(names))}, fields=list(INVOICE_FIELDS))
	return {row.name: row for row in rows}


def _customer_details(customers):
	"""Customer email/mobile and its primary contact's name, email and phone."""
	if not customers:
		return {}
	rows = frappe.get_all(
		"Customer",
		filters={"name": ("in", list(customers))},
		fields=["name", "email_id", "mobile_no", "customer_primary_contact"],
	)
	contact_names = [row.customer_primary_contact for row in rows if row.customer_primary_contact]
	contacts = {}
	if contact_names:
		for contact in frappe.get_all(
			"Contact",
			filters={"name": ("in", contact_names)},
			fields=["name", "full_name", "email_id", "mobile_no", "phone"],
		):
			contacts[contact.name] = contact
	result = {}
	for row in rows:
		contact = contacts.get(row.customer_primary_contact) or {}
		result[row.name] = {
			"email_id": row.email_id,
			"mobile_no": row.mobile_no,
			"primary_contact": row.customer_primary_contact,
			"primary_contact_name": contact.get("full_name"),
			"primary_email": contact.get("email_id"),
			"primary_phone": contact.get("mobile_no") or contact.get("phone"),
		}
	return result


def _last_contact_rows(invoice_names):
	"""Last sent email and last submitted dunning per Sales Invoice.

	Returns {invoice: {"email_date": date | None, "dunning": {date, level} | None}}. Each source
	is read only when the user may read its doctype.
	"""
	names = list(invoice_names or [])
	result = {name: {"email_date": None, "dunning": None} for name in names}
	if not names:
		return result
	if frappe.has_permission("Communication", "read"):
		for row in frappe.db.sql(
			"""
			select reference_name, max(communication_date) as last_date
			from `tabCommunication`
			where reference_doctype = 'Sales Invoice' and reference_name in %(names)s
				and communication_type = 'Communication' and sent_or_received = 'Sent'
			group by reference_name
			""",
			{"names": names},
			as_dict=True,
		):
			result[row.reference_name]["email_date"] = row.last_date
	if frappe.has_permission("Dunning", "read"):
		for row in frappe.db.sql(
			"""
			select op.sales_invoice, d.posting_date, op.dunning_level
			from `tabOverdue Payment` op
			inner join `tabDunning` d on d.name = op.parent and op.parenttype = 'Dunning'
			where d.docstatus = 1 and op.sales_invoice in %(names)s
			order by d.posting_date, op.dunning_level
			""",
			{"names": names},
			as_dict=True,
		):
			# Ordered ascending, so the last row per invoice wins.
			result[row.sales_invoice]["dunning"] = {"date": row.posting_date, "level": row.dunning_level}
	return result


# --- assembly ------------------------------------------------------------------------


def build_receivables(
	*, company, currency, today_date, report_rows, invoice_details, customer_details, contact_rows, companies
):
	"""Assemble the response from query rows (see module docstring)."""
	today_date = getdate(today_date)
	items = []
	for row in report_rows:
		if row.get("party_type") and row.get("party_type") != "Customer":
			continue
		voucher_no = row.get("voucher_no")
		last = contact_rows.get(voucher_no) or {}
		items.append(
			rc.invoice_item(
				row,
				today_date,
				currency,
				details=invoice_details.get(voucher_no),
				customer=customer_details.get(row.get("party")),
				last=rc.latest_contact(last.get("email_date"), last.get("dunning")),
			)
		)
	items.sort(key=rc.invoice_sort_key)
	customers = rc.group_by_customer(items, customer_details)
	return {
		"company": company,
		"currency": currency,
		"today": str(today_date),
		"companies": companies,
		"totals": rc.totals(items, customers),
		"buckets": rc.aging_buckets(items),
		"customers": customers,
		"invoices": items,
	}


@frappe.whitelist()
@frappe.read_only()
def get_receivables(company=None):
	"""Open sales invoices of one company, by customer and age, with contact and last contact."""
	_check_permission()
	company = _resolve_company(company)
	report_date = today()
	rows = _report_rows(company, report_date)
	invoice_names = [row["voucher_no"] for row in rows if row.get("voucher_type") == REPORT_REF_DOCTYPE]
	result = build_receivables(
		company=company,
		currency=frappe.get_cached_value("Company", company, "default_currency"),
		today_date=report_date,
		report_rows=rows,
		invoice_details=_invoice_details(invoice_names),
		customer_details=_customer_details({row["party"] for row in rows if row.get("party")}),
		contact_rows=_last_contact_rows(invoice_names),
		companies=_readable_companies(),
	)
	result["generated_at"] = str(now_datetime())
	return result
