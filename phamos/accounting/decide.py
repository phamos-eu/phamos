# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Decide what happens with a receipt after the AI read it.

Deterministic checks, each adding flags with a reason a person can read:

- the supplier is set and has a history (earlier receipts or invoices),
- the amount fits that history (median and spread of earlier amounts),
- no duplicate (same supplier and invoice number, or same amount a few days apart),
- the document is a voucher (not a contract, reminder or statement),
- the data is complete and the totals add up,
- every line has an expense account.

The decision:
- not_a_voucher: contracts, reminders, statements; a person decides what to do with it,
- needs_human: any warning or blocking flag, from these checks or from earlier steps,
- auto_datev: all clear and the receipt says it is paid; ready to send to DATEV,
- approve_to_pay: all clear and unpaid; ready for a person to approve.

The receipt moves from Inbox to Needs Decision; the queue shows the reasons. Sending to
DATEV automatically is off unless the skill's params switch it on.
"""

import statistics

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, cstr, flt, getdate, nowdate

from phamos.ai_agents.context import PASSED, SkillResult

DEFAULT_PARAMS = {
	"min_history": 2,
	"history_months": 18,
	"amount_tolerance_pct": 30,
	"duplicate_days": 3,
	"auto_datev": 0,
	"auto_datev_min_confidence": 90,
}
DONE_STATUSES = ("Approved to Pay", "Sent to DATEV", "Paid")
NOT_A_VOUCHER = ("Contract", "Reminder", "Statement")
PAID_WORDS = ("paid", "bezahlt")


def params_of(skill=None):
	import json

	params = dict(DEFAULT_PARAMS)
	raw = skill.get("params") if skill else None
	if raw:
		params.update(json.loads(raw) if isinstance(raw, str) else raw)
	return params


def run_decide_skill(ctx, skill):
	"""Check the receipt and decide: send to DATEV, approve to pay, or ask a person."""
	params = params_of(skill)
	extraction = ctx.analysis.get("extraction") or {}
	result = evaluate(ctx.doc, params, extraction=extraction, earlier_flags=ctx.flags)
	ctx.analysis["decision"] = result
	ctx.decision = result["decision"]
	apply_decision(ctx.doc, result, params)
	return SkillResult(PASSED, confidence=result["confidence"], flags=result["flags"], message=result["summary"],
		output={"decision": result["decision"]})


def evaluate(doc, params=None, extraction=None, earlier_flags=None):
	"""{decision, confidence, flags, summary, paid, history} for a receipt. Changes nothing."""
	params = params or dict(DEFAULT_PARAMS)
	flags = []

	def flag(code, severity, message, field=None):
		flags.append({"code": code, "severity": severity, "message": message, "field": field})

	# --- the document itself
	if doc.receipt_type in NOT_A_VOUCHER:
		flag("not_a_voucher", "block", _("{0}: not a voucher. Decide what to do with it.").format(_(doc.receipt_type)), "receipt_type")
	if not flt(doc.sum):
		flag("no_amount", "block", _("No amount."), "sum")
	if not doc.posting_date:
		flag("no_date", "block", _("No date."), "posting_date")
	if not doc.supplier_reference:
		flag("no_reference", "warn", _("No invoice number."), "supplier_reference")
	net, tax, gross = flt(doc.net_total), flt(doc.total_taxes), flt(doc.sum)
	if net and gross and abs(net + tax - gross) > 0.02:
		flag("totals_inconsistent", "block", _("Net {0} + tax {1} is not the total {2}.").format(net, tax, gross), "sum")
	lines = doc.get("items") or []
	if lines and not any(f.get("code") == "account_unclear" for f in earlier_flags or []):
		missing = [row.item_name for row in lines if not row.expense_account]
		if missing:
			flag("line_without_account", "warn", _("{0} lines have no expense account.").format(len(missing)), "items")

	# --- supplier and history
	history = supplier_history(doc, params)
	if not doc.supplier:
		flag("no_supplier", "block", _("No supplier."), "supplier")
	elif history["count"] < cint(params["min_history"]):
		flag("new_supplier", "warn", _("New supplier: {0} earlier receipts or invoices.").format(history["count"]), "supplier")
	amount_note = amount_check(doc, history, params)
	if amount_note:
		flag("unusual_amount", "warn", amount_note, "sum")

	# --- duplicates
	for code, severity, message in duplicates(doc, params):
		flag(code, severity, message, "supplier_reference")

	# --- paid?
	paid = bool(doc.is_paid) or cstr(extraction.get("payment_status") if extraction else "").lower() in PAID_WORDS
	if paid and not doc.is_paid:
		how = cstr((extraction or {}).get("paid_with"))
		flags.append({"code": "says_paid", "severity": "info", "field": "is_paid",
			"message": _("The receipt says it is paid{0}.").format(f" ({how})" if how else "")})

	all_flags = list(earlier_flags or []) + flags
	blocks = sum(1 for f in all_flags if f.get("severity") == "block")
	warns = sum(1 for f in all_flags if f.get("severity") == "warn")
	confidence = max(0, 100 - 30 * blocks - 15 * warns)
	if any(f["code"] == "not_a_voucher" for f in flags):
		decision = "not_a_voucher"
	elif blocks or warns:
		decision = "needs_human"
	elif paid:
		decision = "auto_datev"
	else:
		decision = "approve_to_pay"
	return {
		"decision": decision,
		"confidence": confidence,
		"flags": flags,
		"paid": paid,
		"history": history,
		"summary": summary_of(decision, blocks + warns),
	}


def summary_of(decision, problems):
	return {
		"not_a_voucher": _("Not a voucher; a person decides."),
		"needs_human": _("Needs a decision: {0} points to check.").format(problems),
		"auto_datev": _("All clear and paid: ready to send to DATEV."),
		"approve_to_pay": _("All clear: ready to approve to pay."),
	}[decision]


def supplier_history(doc, params):
	"""Earlier, accepted receipts and invoices of the supplier: count and amounts (company currency)."""
	if not doc.supplier:
		return {"count": 0, "amounts": []}
	since = add_months(getdate(doc.posting_date or nowdate()), -cint(params["history_months"]))
	receipts = frappe.get_all(
		"Accounting Receipt",
		filters={"supplier": doc.supplier, "name": ("!=", doc.name), "status": ("in", DONE_STATUSES),
			"posting_date": (">=", since), "is_return": 0},
		fields=["sum_in_company_currency", "sum", "purchase_invoice"],
	)
	linked = {r.purchase_invoice for r in receipts if r.purchase_invoice}
	invoices = frappe.get_all(
		"Purchase Invoice",
		filters={"supplier": doc.supplier, "docstatus": 1, "is_return": 0, "posting_date": (">=", since),
			"name": ("not in", list(linked) or [""])},
		fields=["name", "base_grand_total"],
	)
	invoices = [i for i in invoices if i.name != doc.purchase_invoice]
	amounts = [flt(r.sum_in_company_currency or r.sum) for r in receipts] + [flt(i.base_grand_total) for i in invoices]
	return {"count": len(receipts) + len(invoices), "amounts": [a for a in amounts if a]}


def amount_check(doc, history, params):
	"""A sentence when the amount is far from what the supplier usually charges, else None."""
	amounts = history["amounts"]
	amount = flt(doc.sum_in_company_currency or doc.sum)
	if len(amounts) < 3 or not amount:
		return None
	median = statistics.median(amounts)
	spread = 1.4826 * statistics.median([abs(a - median) for a in amounts])
	within_tolerance = median and abs(amount - median) <= median * flt(params["amount_tolerance_pct"]) / 100
	within_spread = spread and abs(amount - median) <= 2 * spread
	if within_tolerance or within_spread:
		return None
	change = (amount - median) / median * 100 if median else 0
	return _("Amount {0} is {1:+.0f} % against the usual {2} ({3} earlier).").format(
		frappe.format(amount, {"fieldtype": "Currency"}), change, frappe.format(median, {"fieldtype": "Currency"}), len(amounts)
	)


def _normalized_reference(value):
	return "".join(c for c in cstr(value).upper() if c.isalnum())


def duplicates(doc, params):
	"""[(code, severity, message)] for likely duplicates of this receipt."""
	if not doc.supplier:
		return []
	found = []
	reference = _normalized_reference(doc.supplier_reference)
	others = frappe.get_all(
		"Accounting Receipt",
		filters={"supplier": doc.supplier, "name": ("!=", doc.name), "status": ("!=", "Cancelled")},
		fields=["name", "supplier_reference", "sum", "posting_date"],
	)
	for other in others:
		if reference and _normalized_reference(other.supplier_reference) == reference:
			found.append(("duplicate", "block", _("Same invoice number as {0}: possibly a duplicate.").format(other.name)))
		elif (
			flt(doc.sum) and abs(flt(other.sum) - flt(doc.sum)) <= 0.01 and doc.posting_date and other.posting_date
			and abs((getdate(other.posting_date) - getdate(doc.posting_date)).days) <= cint(params["duplicate_days"])
		):
			found.append(("possible_duplicate", "warn", _("Same amount as {0} a few days apart.").format(other.name)))
	return found[:3]


def apply_decision(doc, result, params):
	"""Store the decision; move Inbox receipts to Needs Decision; optionally send to DATEV."""
	values = {"ai_decision": result["decision"]}
	if doc.status == "Inbox":
		values["status"] = "Needs Decision"
	doc.db_set(values, update_modified=False)
	if (
		cint(params.get("auto_datev"))
		and result["decision"] == "auto_datev"
		and result["confidence"] >= flt(params["auto_datev_min_confidence"])
		and not doc.sent_to_datev
	):
		from phamos.phamos.doctype.accounting_receipt.accounting_receipt import send_to_datev

		send_to_datev(doc.name)
