# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Accounting Cockpit statistics and payment calendar (#1369).

`get_receipt_dashboard` answers "what came in, what was booked, where are the peaks and
what is still to pay"; `get_payment_calendar` lists what has to be paid when. Queries are
small helpers returning plain rows; `build_dashboard` / `build_calendar` assemble them
with the pure rules in `phamos.accounting.statistics`, so tests patch the queries.
"""

from collections import defaultdict
from datetime import timedelta

import frappe
from erpnext.setup.utils import get_exchange_rate
from frappe import _
from frappe.utils import cint, flt, getdate, today

from phamos.accounting import statistics as st
from phamos.api.dashboard_metrics import percentile

RECEIPT = "Accounting Receipt"
OPEN_TO_PAY_STATUSES = ("Approved to Pay", "Sent to DATEV")
BOOKED_VOUCHER_TYPES = ("Purchase Invoice", "Journal Entry", "Expense Claim")
CLOSED_PAYMENT_REQUEST_STATUSES = ("Paid", "Cancelled", "Completed")
STATUS_THEMES = {
	"Inbox": "gray",
	"Needs Decision": "amber",
	"Approved to Pay": "blue",
	"Do Not Pay": "gray",
	"Sent to DATEV": "blue",
	"Paid": "green",
}
CACHE_SECONDS = 300
TOP_LIMIT = 8
PEAK_SUPPLIERS = 3
CALENDAR_MAX_DAYS = 120

# Receipt amount in company currency, negative for returns (credit notes).
_AMOUNT_SQL = """
	(case when r.is_return = 1 then -1 else 1 end) * coalesce(
		nullif(r.sum_in_company_currency, 0),
		r.`sum` * coalesce(nullif(r.conversion_rate, 0), 1),
		0
	)
"""


def can_read_statistics():
	return bool(frappe.has_permission(RECEIPT, "read") and frappe.has_permission("GL Entry", "read"))


def _check_permission():
	if not can_read_statistics():
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _resolve_company(company):
	company = company or frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	if not company:
		company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
	if not company or not frappe.db.exists("Company", company):
		frappe.throw(_("No company found"))
	# The queries below aggregate with raw SQL, which skips User Permissions; checking the
	# Company document applies them, so a user limited to one company cannot read another.
	if not frappe.has_permission("Company", "read", doc=company):
		frappe.throw(_("Not permitted to see figures of {0}").format(company), frappe.PermissionError)
	return company


# --- queries -------------------------------------------------------------------------


def _receipt_rows(company, start, end):
	"""Non-cancelled receipts per posting day and supplier: count and gross amount."""
	return frappe.db.sql(
		f"""
		select r.posting_date, r.supplier, max(r.supplier_name) as supplier_name,
			count(*) as count, sum({_AMOUNT_SQL}) as amount
		from `tabAccounting Receipt` r
		where r.company = %(company)s and r.posting_date >= %(start)s and r.posting_date < %(end)s
			and ifnull(r.status, '') != 'Cancelled'
		group by r.posting_date, r.supplier
		""",
		{"company": company, "start": start, "end": end},
		as_dict=True,
	)


def _gl_rows(company, start, end):
	"""Booked expense (debit − credit) per day, voucher type, account and cost center."""
	return frappe.db.sql(
		"""
		select gle.posting_date, gle.voucher_type, gle.account, gle.cost_center,
			sum(gle.debit - gle.credit) as amount
		from `tabGL Entry` gle
		inner join `tabAccount` acc on acc.name = gle.account
		where gle.company = %(company)s and gle.is_cancelled = 0
			and gle.posting_date >= %(start)s and gle.posting_date < %(end)s
			and gle.voucher_type in %(voucher_types)s
			and acc.root_type = 'Expense' and acc.is_group = 0
		group by gle.posting_date, gle.voucher_type, gle.account, gle.cost_center
		""",
		{"company": company, "start": start, "end": end, "voucher_types": BOOKED_VOUCHER_TYPES},
		as_dict=True,
	)


def _open_receipt_rows(company):
	"""Approved, unpaid receipts (Approved to Pay / Sent to DATEV, is_paid = 0)."""
	return frappe.db.sql(
		f"""
		select r.name, r.title, r.status, r.supplier, r.supplier_name, r.supplier_reference,
			r.due_date, r.posting_date, r.`sum`, r.currency, r.purchase_invoice,
			{_AMOUNT_SQL} as amount
		from `tabAccounting Receipt` r
		where r.company = %(company)s and r.status in %(statuses)s and ifnull(r.is_paid, 0) = 0
		order by r.due_date, r.name
		""",
		{"company": company, "statuses": OPEN_TO_PAY_STATUSES},
		as_dict=True,
	)


def _status_rows(company):
	return frappe.db.sql(
		f"""
		select ifnull(nullif(r.status, ''), 'Inbox') as status, count(*) as count, sum({_AMOUNT_SQL}) as amount
		from `tabAccounting Receipt` r
		where r.company = %(company)s and ifnull(r.status, '') != 'Cancelled'
		group by ifnull(nullif(r.status, ''), 'Inbox')
		""",
		{"company": company},
		as_dict=True,
	)


def _waiting_rows(company):
	"""Receipts waiting for a human: Inbox and Needs Decision, with their creation day."""
	return frappe.db.sql(
		"""
		select r.name, ifnull(nullif(r.status, ''), 'Inbox') as status, date(r.creation) as created
		from `tabAccounting Receipt` r
		where r.company = %(company)s and ifnull(nullif(r.status, ''), 'Inbox') in ('Inbox', 'Needs Decision')
		""",
		{"company": company},
		as_dict=True,
	)


def _ai_rows(company, since):
	"""AI decisions of the last 30 days, once the AI accountant fields exist (plan Phase 1)."""
	meta = frappe.get_meta(RECEIPT)
	if not (meta.has_field("ai_decision") and meta.has_field("ai_confidence")):
		return None
	return frappe.db.sql(
		"""
		select r.ai_decision, r.ai_confidence
		from `tabAccounting Receipt` r
		where r.company = %(company)s and r.creation >= %(since)s and ifnull(r.ai_decision, '') != ''
		""",
		{"company": company, "since": since},
		as_dict=True,
	)


def _payment_request_rows(company):
	"""Open outward Payment Requests that no Accounting Receipt represents yet.

	A request is represented when it points at a receipt itself or at a receipt's
	Purchase Invoice; the receipt is then the calendar entry. The due date comes from the
	Purchase Invoice when there is one.
	"""
	if not frappe.has_permission("Payment Request", "read"):
		return []
	return frappe.db.sql(
		"""
		select pr.name, pr.status, pr.party_type, pr.party, pr.party_name, pr.reference_doctype,
			pr.reference_name, pr.transaction_date, pr.grand_total, pr.currency,
			pi.due_date as invoice_due_date, pi.supplier as invoice_supplier, pi.supplier_name as invoice_supplier_name,
			pi.currency as invoice_currency, pi.conversion_rate as invoice_conversion_rate
		from `tabPayment Request` pr
		left join `tabPurchase Invoice` pi
			on pr.reference_doctype = 'Purchase Invoice' and pi.name = pr.reference_name
		where pr.company = %(company)s and pr.docstatus < 2 and pr.payment_request_type = 'Outward'
			and ifnull(pr.status, '') not in %(closed)s
			and not exists (
				select 1 from `tabAccounting Receipt` r
				where (pr.reference_doctype = 'Accounting Receipt' and r.name = pr.reference_name)
					or (pr.reference_doctype = 'Purchase Invoice' and r.purchase_invoice = pr.reference_name)
			)
		""",
		{"company": company, "closed": CLOSED_PAYMENT_REQUEST_STATUSES},
		as_dict=True,
	)


def payment_request_amount(row, company_currency):
	"""A Payment Request's grand total in company currency.

	Requests carry only their own currency, so a USD request is converted with its Purchase
	Invoice's rate when the invoice is in the same currency, else with the exchange rate of
	the request date.
	"""
	amount = flt(row.get("grand_total"))
	currency = row.get("currency")
	if not currency or currency == company_currency:
		return amount
	if row.get("invoice_currency") == currency and flt(row.get("invoice_conversion_rate")):
		return amount * flt(row["invoice_conversion_rate"])
	rate = get_exchange_rate(currency, company_currency, row.get("transaction_date"))
	return amount * flt(rate or 1)


# --- dashboard -----------------------------------------------------------------------


def _strip_abbr(name, abbr):
	suffix = f" - {abbr}" if abbr else ""
	return name[: -len(suffix)] if suffix and name and name.endswith(suffix) else name


def _month_key(value):
	value = getdate(value)
	return (value.year, value.month)


def _top(amounts, limit=TOP_LIMIT):
	return sorted(amounts.items(), key=lambda item: -item[1])[:limit]


def _window_values(window, receipts, gl):
	divisor = window["divisor"]
	start, end = window["start"], window["end"]
	return {
		"label": window["label"],
		"start": str(start),
		"end": str(end - timedelta(days=1)),
		"receipts_count": st.sum_rows(receipts, start, end, "posting_date", "count") / divisor,
		"receipts_sum": flt(st.sum_rows(receipts, start, end, "posting_date", "amount") / divisor, 2),
		"booked": flt(st.sum_rows(gl, start, end, "posting_date", "amount") / divisor, 2),
	}


def build_dashboard(
	*, company, currency, abbr, today_date, months, receipts, gl, open_rows, status_rows, waiting_rows, ai_rows
):
	"""Assemble the dashboard response from query rows (see module docstring)."""
	today_date = getdate(today_date)
	windows = st.month_windows(today_date, months)
	history = st.month_windows(today_date, months + 12)

	by_month = defaultdict(lambda: {"count": 0, "amount": 0.0, "pi": 0.0, "je": 0.0})
	suppliers_by_month = defaultdict(lambda: defaultdict(lambda: {"amount": 0.0, "count": 0}))
	supplier_names = {}
	for row in receipts:
		key = _month_key(row["posting_date"])
		by_month[key]["count"] += cint(row.get("count"))
		by_month[key]["amount"] += flt(row.get("amount"))
		supplier = row.get("supplier") or ""
		supplier_names[supplier] = row.get("supplier_name") or supplier or _("No supplier")
		suppliers_by_month[key][supplier]["amount"] += flt(row.get("amount"))
		suppliers_by_month[key][supplier]["count"] += cint(row.get("count"))
	for row in gl:
		key = _month_key(row["posting_date"])
		bucket = "pi" if row.get("voucher_type") == "Purchase Invoice" else "je"
		by_month[key][bucket] += flt(row.get("amount"))

	# Spikes judge full months only; the series reaches 12 months further back for
	# the three-month average and the same month last year.
	full_history = [w for w in history if not w["mtd"]]
	spikes = st.detect_spikes([by_month[_month_key(w["start"])]["amount"] for w in full_history])
	spike_by_key = {_month_key(w["start"]): spike for w, spike in zip(full_history, spikes, strict=True)}

	monthly, peaks = [], []
	for window in windows:
		key = _month_key(window["start"])
		last_year_key = (key[0] - 1, key[1])
		values = by_month[key]
		end = window["end"] - timedelta(days=1)
		spike = spike_by_key.get(key)
		if spike:
			top = sorted(suppliers_by_month[key].items(), key=lambda item: -item[1]["amount"])[:PEAK_SUPPLIERS]
			spike = {
				**spike,
				"top_suppliers": [
					{"supplier": s, "supplier_name": supplier_names.get(s, s), "amount": flt(v["amount"], 2), "count": v["count"]}
					for s, v in top
				],
			}
			peaks.append(
				{
					"label": st.month_label(window["start"], with_year=True),
					"start": str(window["start"]),
					"end": str(end),
					"route": {"path": "/receipts", "query": {"from": str(window["start"]), "to": str(end)}},
					**spike,
				}
			)
		monthly.append(
			{
				"label": window["label"],
				"start": str(window["start"]),
				"end": str(end),
				"mtd": window["mtd"],
				"receipts_count": values["count"],
				"receipts_sum": flt(values["amount"], 2),
				"booked_pi": flt(values["pi"], 2),
				"booked_je": flt(values["je"], 2),
				"last_year_count": by_month[last_year_key]["count"],
				"last_year_sum": flt(by_month[last_year_key]["amount"], 2),
				"spike": spike,
			}
		)
	# Red peaks first (newest first), recurring months after them.
	peaks.sort(key=lambda peak: peak["start"], reverse=True)
	peaks.sort(key=lambda peak: peak["kind"] != "peak")

	comparison = {name: _window_values(w, receipts, gl) for name, w in st.comparison_windows(today_date).items()}

	window_start = windows[0]["start"]
	trailing = [row for row in receipts if getdate(row["posting_date"]) >= window_start]
	supplier_totals = defaultdict(float)
	for row in trailing:
		supplier_totals[row.get("supplier") or ""] += flt(row.get("amount"))
	trailing_gl = [row for row in gl if getdate(row["posting_date"]) >= window_start]
	account_totals, cost_center_totals = defaultdict(float), defaultdict(float)
	for row in trailing_gl:
		account_totals[row.get("account")] += flt(row.get("amount"))
		cost_center_totals[row.get("cost_center") or ""] += flt(row.get("amount"))

	overdue = [row for row in open_rows if row.get("due_date") and getdate(row["due_date"]) < today_date]
	waiting = [row for row in waiting_rows if row.get("status") == "Needs Decision"]

	return {
		"company": company,
		"currency": currency,
		"today": str(today_date),
		"windows": comparison,
		"monthly": monthly,
		"peaks": peaks,
		"open_to_pay": {
			"count": len(open_rows),
			"amount": flt(sum(flt(r.get("amount")) for r in open_rows), 2),
			"overdue_count": len(overdue),
			"overdue_amount": flt(sum(flt(r.get("amount")) for r in overdue), 2),
		},
		"queue": {
			"needs_decision": len(waiting),
			"inbox": sum(1 for row in waiting_rows if row.get("status") == "Inbox"),
			**st.age_summary([row.get("created") for row in waiting], today_date),
		},
		"ai": _ai_summary(ai_rows),
		"status": [
			{
				"key": row["status"],
				"label": row["status"],
				"value": cint(row["count"]),
				"amount": flt(row.get("amount"), 2),
				"theme": STATUS_THEMES.get(row["status"], "gray"),
			}
			for row in sorted(status_rows, key=lambda r: list(STATUS_THEMES).index(r["status"]) if r["status"] in STATUS_THEMES else 99)
		],
		"aging": st.aging_buckets(open_rows, today_date),
		"top_suppliers": [
			{"key": s, "label": supplier_names.get(s) or s or _("No supplier"), "value": flt(v, 2)}
			for s, v in _top(supplier_totals)
		],
		"by_expense_account": [
			{"key": a, "label": _strip_abbr(a, abbr), "value": flt(v, 2)} for a, v in _top(account_totals) if v
		],
		"by_cost_center": [
			{"key": c, "label": _strip_abbr(c, abbr) or _("No cost center"), "value": flt(v, 2)}
			for c, v in _top(cost_center_totals)
			if v
		],
	}


def _ai_summary(rows):
	if rows is None:
		return {"available": False}
	confidences = [flt(r.get("ai_confidence")) for r in rows if r.get("ai_confidence") is not None]
	auto = sum(1 for r in rows if r.get("ai_decision") in ("auto_datev", "approve_to_pay"))
	return {
		"available": True,
		"runs": len(rows),
		"auto_ready_share": round(auto / len(rows), 3) if rows else None,
		"median_confidence": percentile(confidences, 50),
	}


@frappe.whitelist()
def get_receipt_dashboard(company=None, months=12):
	"""Receipt and booked-expense statistics for the Accounting Cockpit (cached 5 minutes per company)."""
	_check_permission()
	company = _resolve_company(company)
	months = min(max(cint(months) or 12, 3), 24)
	today_date = getdate(today())
	cache_key = f"phamos:accounting_stats:{company}:{months}:{today_date}"
	# expires=True: without it get_value pins a miss (None) in the request-local cache.
	cached = frappe.cache.get_value(cache_key, expires=True)
	if cached:
		return cached

	currency, abbr = frappe.get_cached_value("Company", company, ["default_currency", "abbr"])
	start = st.add_months(today_date, -(months + 12 - 1))
	end = today_date + timedelta(days=1)
	result = build_dashboard(
		company=company,
		currency=currency,
		abbr=abbr,
		today_date=today_date,
		months=months,
		receipts=_receipt_rows(company, start, end),
		gl=_gl_rows(company, start, end),
		open_rows=_open_receipt_rows(company),
		status_rows=_status_rows(company),
		waiting_rows=_waiting_rows(company),
		ai_rows=_ai_rows(company, today_date - timedelta(days=30)),
	)
	frappe.cache.set_value(cache_key, result, expires_in_sec=CACHE_SECONDS)
	return result


# --- payment calendar ----------------------------------------------------------------


def _receipt_item(row, today_date):
	due = getdate(row["due_date"]) if row.get("due_date") else None
	return {
		"kind": "receipt",
		"name": row["name"],
		"title": row.get("supplier_name") or row.get("title") or row["name"],
		"reference": row.get("supplier_reference"),
		"supplier": row.get("supplier"),
		"date": str(due) if due else None,
		"amount": flt(row.get("amount"), 2),
		"document_amount": flt(row.get("sum"), 2),
		"currency": row.get("currency"),
		"status": row.get("status"),
		"days_overdue": (today_date - due).days if due and due < today_date else 0,
		"route": f"/receipts/{row['name']}",
	}


def _payment_request_item(row, today_date, company_currency):
	due = getdate(row.get("invoice_due_date") or row.get("transaction_date"))
	return {
		"kind": "payment_request",
		"name": row["name"],
		"title": row.get("party_name") or row.get("invoice_supplier_name") or row.get("party") or row["name"],
		"reference": row.get("reference_name"),
		"supplier": row.get("invoice_supplier") or (row.get("party") if row.get("party_type") == "Supplier" else None),
		"date": str(due) if due else None,
		"amount": flt(payment_request_amount(row, company_currency), 2),
		"document_amount": flt(row.get("grand_total"), 2),
		"currency": row.get("currency"),
		"status": row.get("status"),
		"days_overdue": (today_date - due).days if due and due < today_date else 0,
		"desk_url": f"/app/payment-request/{row['name']}",
	}


def build_calendar(*, from_date, to_date, today_date, receipt_rows, payment_request_rows, currency):
	"""Group open payables into days and ISO weeks of [from_date, to_date]; overdue and undated apart."""
	from_date, to_date, today_date = getdate(from_date), getdate(to_date), getdate(today_date)
	all_items = [_receipt_item(row, today_date) for row in receipt_rows]
	all_items += [_payment_request_item(row, today_date, currency) for row in payment_request_rows]

	items, undated, overdue_items = [], [], []
	for item in all_items:
		if not item["date"]:
			undated.append(item)
			continue
		day = getdate(item["date"])
		if day < today_date:
			overdue_items.append(item)
		if from_date <= day <= to_date:
			items.append(item)
	items.sort(key=lambda item: (item["date"], -item["amount"]))
	overdue_items.sort(key=lambda item: (item["date"], -item["amount"]))

	totals_by_day = {}
	for item in items:
		day = totals_by_day.setdefault(item["date"], {"count": 0, "amount": 0.0})
		day["count"] += 1
		day["amount"] = flt(day["amount"] + item["amount"], 2)

	weeks = []
	for week in st.iso_weeks(from_date, to_date):
		in_week = [item for item in items if week["start"] <= getdate(item["date"]) <= week["end"]]
		weeks.append(
			{
				**week,
				"start": str(week["start"]),
				"end": str(week["end"]),
				"count": len(in_week),
				"amount": flt(sum(item["amount"] for item in in_week), 2),
			}
		)

	return {
		"from_date": str(from_date),
		"to_date": str(to_date),
		"today": str(today_date),
		"currency": currency,
		"items": items,
		"undated": undated,
		"totals_by_day": totals_by_day,
		"weeks": weeks,
		"totals": {"count": len(items), "amount": flt(sum(item["amount"] for item in items), 2)},
		"overdue": {
			"count": len(overdue_items),
			"amount": flt(sum(item["amount"] for item in overdue_items), 2),
			"items": overdue_items,
		},
	}


@frappe.whitelist()
def get_payment_calendar(from_date, to_date, company=None):
	"""Open payables (approved unpaid receipts and open Payment Requests) between two dates."""
	_check_permission()
	company = _resolve_company(company)
	from_date, to_date = getdate(from_date), getdate(to_date)
	if to_date < from_date:
		frappe.throw(_("The end date is before the start date"))
	if (to_date - from_date).days > CALENDAR_MAX_DAYS:
		frappe.throw(_("Choose a range of at most {0} days").format(CALENDAR_MAX_DAYS))
	return build_calendar(
		from_date=from_date,
		to_date=to_date,
		today_date=today(),
		receipt_rows=_open_receipt_rows(company),
		payment_request_rows=_payment_request_rows(company),
		currency=frappe.get_cached_value("Company", company, "default_currency"),
	)
