# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Accounts Receivable rules for the Accounting Cockpit (#1777). Pure functions, no database.

ERPNext's Accounts Receivable report gives one row per open voucher. These rules turn those
rows into what the cockpit shows: days overdue and an age bucket per invoice, a contact to call,
the last time somebody reminded the customer, and per-customer totals.

Aging is computed here from the due date, not taken from the report's `range1..5`: the report
nets negative rows (unallocated payments, credit notes) into its buckets. Here such rows are
credits: listed, counted in the net outstanding, but kept out of buckets and overdue sums.
"""

from frappe import _
from frappe.utils import flt, getdate

# (key, label, theme, lowest days overdue). Boundaries follow ERPNext's 30/60/90/120 ranges.
AGING_BUCKETS = (
	("not_due", "Not yet due", "green", None),
	("d1_30", "1–30 days overdue", "amber", 1),
	("d31_60", "31–60 days overdue", "red", 31),
	("d61_90", "61–90 days overdue", "red", 61),
	("d91_120", "91–120 days overdue", "red", 91),
	("d120_plus", "Over 120 days overdue", "red", 121),
)
BUCKET_KEYS = tuple(bucket[0] for bucket in AGING_BUCKETS)
PRECISION = 2


def days_overdue(due_date, today):
	"""Days past `due_date` (0 when not yet due or due today)."""
	if not due_date:
		return 0
	return max(0, (getdate(today) - getdate(due_date)).days)


def aging_bucket(days):
	"""Key of AGING_BUCKETS for an invoice `days` overdue."""
	key = "not_due"
	for bucket_key, _label, _theme, lowest in AGING_BUCKETS:
		if lowest is not None and days >= lowest:
			key = bucket_key
	return key


def bucket_rows():
	"""Empty bucket list in display order, same shape as `statistics.aging_buckets`."""
	return [
		{"key": key, "label": _(label), "theme": theme, "value": 0, "amount": 0.0}
		for key, label, theme, _lowest in AGING_BUCKETS
	]


def aging_buckets(items):
	"""Count and sum invoice items per bucket; credits are skipped. All buckets, in order."""
	result = {row["key"]: row for row in bucket_rows()}
	for item in items:
		if item.get("kind") != "invoice":
			continue
		bucket = result[item["bucket"]]
		bucket["value"] += 1
		bucket["amount"] = flt(bucket["amount"] + flt(item.get("outstanding")), PRECISION)
	return list(result.values())


def pick_contact(invoice=None, customer=None):
	"""Whom to contact about an invoice: the invoice's contact, else the customer's primary
	contact, else the customer's own email. Returns None when nothing is known.

	`invoice` carries contact_person/contact_display/contact_email/contact_mobile; `customer`
	carries primary_contact/primary_contact_name/primary_email/primary_phone/email_id/mobile_no.
	"""
	invoice = invoice or {}
	customer = customer or {}
	if invoice.get("contact_email") or invoice.get("contact_person"):
		return {
			"name": invoice.get("contact_display") or invoice.get("contact_person"),
			"email": invoice.get("contact_email") or customer.get("primary_email") or customer.get("email_id"),
			"phone": invoice.get("contact_mobile") or customer.get("primary_phone") or customer.get("mobile_no"),
			"source": "invoice",
		}
	if customer.get("primary_contact"):
		return {
			"name": customer.get("primary_contact_name") or customer.get("primary_contact"),
			"email": customer.get("primary_email") or customer.get("email_id"),
			"phone": customer.get("primary_phone") or customer.get("mobile_no"),
			"source": "primary_contact",
		}
	if customer.get("email_id") or customer.get("mobile_no"):
		return {"name": None, "email": customer.get("email_id"), "phone": customer.get("mobile_no"), "source": "customer"}
	return None


def latest_contact(email_date=None, dunning=None):
	"""The later of the last sent email and the last submitted dunning, or None.

	`dunning` is {date, level}. On the same day the dunning wins: it says more.
	"""
	candidates = []
	if email_date:
		candidates.append({"date": str(getdate(email_date)), "kind": "email", "level": None})
	if dunning and dunning.get("date"):
		candidates.append({"date": str(getdate(dunning["date"])), "kind": "dunning", "level": dunning.get("level")})
	if not candidates:
		return None
	return max(candidates, key=lambda c: (c["date"], c["kind"] == "dunning"))


def later_contact(a, b):
	"""The later of two `latest_contact` results (either may be None)."""
	if not a or not b:
		return a or b
	return max(a, b, key=lambda c: (c["date"], c["kind"] == "dunning"))


def invoice_item(row, today, company_currency, details=None, customer=None, last=None):
	"""One cockpit item from a report row. `details` are Sales Invoice fields, `customer` the
	customer's contact data, `last` the voucher's `latest_contact`."""
	details = details or {}
	outstanding = flt(row.get("outstanding"), PRECISION)
	kind = "invoice" if outstanding > 0 else "credit"
	due_date = row.get("due_date")
	# Rows without a due date (Journal Entries) age by posting date, as the report does.
	age_from = due_date or row.get("posting_date")
	days = days_overdue(age_from, today) if kind == "invoice" else 0
	document_currency = details.get("currency")
	foreign = bool(document_currency and document_currency != company_currency)
	return {
		"kind": kind,
		"voucher_type": row.get("voucher_type"),
		"voucher_no": row.get("voucher_no"),
		"customer": row.get("party"),
		"customer_name": row.get("customer_name") or row.get("party"),
		"po_no": details.get("po_no") or row.get("po_no"),
		"status": details.get("status"),
		"posting_date": str(getdate(row["posting_date"])) if row.get("posting_date") else None,
		"due_date": str(getdate(due_date)) if due_date else None,
		"days_overdue": days,
		"bucket": aging_bucket(days) if kind == "invoice" else None,
		"outstanding": outstanding,
		"invoiced": flt(row.get("invoiced"), PRECISION),
		"paid": flt(row.get("paid"), PRECISION),
		"credit_note": flt(row.get("credit_note"), PRECISION),
		"document_currency": document_currency if foreign else None,
		"document_outstanding": flt(details.get("outstanding_amount"), PRECISION) if foreign else None,
		"contact": pick_contact(details, customer),
		"last_contact": last,
	}


def invoice_sort_key(item):
	"""Invoices first (most overdue, then largest), credits last."""
	return (item["kind"] != "invoice", -item["days_overdue"], -item["outstanding"], item["voucher_no"] or "")


def group_by_customer(items, customers=None):
	"""Per-customer totals of `items` (already built with `invoice_item`), most overdue first.

	`customers` maps customer → contact data, used when no open invoice names a contact.
	"""
	customers = customers or {}
	groups = {}
	for item in items:
		group = groups.get(item["customer"])
		if group is None:
			group = groups[item["customer"]] = {
				"customer": item["customer"],
				"customer_name": item["customer_name"],
				"outstanding": 0.0,
				"overdue": 0.0,
				"not_due": 0.0,
				"credits": 0.0,
				"invoice_count": 0,
				"overdue_count": 0,
				"oldest_days_overdue": 0,
				"buckets": dict.fromkeys(BUCKET_KEYS, 0.0),
				"contact": None,
				"last_contact": None,
				"_contact_posting": "",
			}
		amount = item["outstanding"]
		group["outstanding"] = flt(group["outstanding"] + amount, PRECISION)
		group["last_contact"] = later_contact(group["last_contact"], item["last_contact"])
		if item["kind"] == "credit":
			group["credits"] = flt(group["credits"] + amount, PRECISION)
			continue
		group["invoice_count"] += 1
		group["buckets"][item["bucket"]] = flt(group["buckets"][item["bucket"]] + amount, PRECISION)
		if item["days_overdue"] > 0:
			group["overdue"] = flt(group["overdue"] + amount, PRECISION)
			group["overdue_count"] += 1
			group["oldest_days_overdue"] = max(group["oldest_days_overdue"], item["days_overdue"])
		else:
			group["not_due"] = flt(group["not_due"] + amount, PRECISION)
		# The contact of the most recent open invoice speaks for the customer.
		if item["contact"] and (item["posting_date"] or "") >= group["_contact_posting"]:
			group["contact"] = item["contact"]
			group["_contact_posting"] = item["posting_date"] or ""

	result = []
	for group in groups.values():
		group.pop("_contact_posting")
		if not group["contact"]:
			group["contact"] = pick_contact(None, customers.get(group["customer"]))
		result.append(group)
	result.sort(key=lambda g: (-g["overdue"], -g["outstanding"], g["customer_name"] or ""))
	return result


def totals(items, customer_rows):
	"""Headline figures over all items and customers."""
	invoices = [item for item in items if item["kind"] == "invoice"]
	credits = [item for item in items if item["kind"] == "credit"]
	overdue = [item for item in invoices if item["days_overdue"] > 0]
	oldest = max(overdue, key=lambda item: item["days_overdue"], default=None)
	return {
		"outstanding": flt(sum(item["outstanding"] for item in items), PRECISION),
		"invoice_count": len(invoices),
		"customer_count": len(customer_rows),
		"overdue_amount": flt(sum(item["outstanding"] for item in overdue), PRECISION),
		"overdue_count": len(overdue),
		"customers_overdue": sum(1 for row in customer_rows if row["overdue_count"]),
		"not_due_amount": flt(sum(item["outstanding"] for item in invoices if not item["days_overdue"]), PRECISION),
		"not_due_count": len(invoices) - len(overdue),
		"credits_amount": flt(sum(item["outstanding"] for item in credits), PRECISION),
		"credits_count": len(credits),
		"oldest_days_overdue": oldest["days_overdue"] if oldest else 0,
		"oldest_customer_name": oldest["customer_name"] if oldest else None,
	}
