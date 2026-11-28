# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Learn from people correcting what the AI read.

When a person saves a receipt, the values the latest AI run wrote (its `fields_set`,
values in `analysis.extraction.values`) are compared with what the receipt now holds.
Differences are corrections: stored on the run (outcome Corrected) and, for fields the
AI reads from the PDF text, turned into a *suggested* reading rule for that supplier.

A suggestion is an AI Skill (phase Extract, scoped to the supplier, origin Suggested,
disabled) with one prompt rule. Nothing is applied until a person accepts it in the
cockpit. The same correction again raises its count instead of creating a new one; a
dismissed suggestion is never suggested again.

Expense-account corrections do not go through here: the assignment library learns them.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate

LEARNED_FIELDS = (
	"supplier_reference", "posting_date", "due_date", "sum", "net_total", "total_taxes", "supplier",
	"currency", "receipt_type", "supplier_tax_id", "supplier_iban", "payment_reference",
)
RULE_FIELDS = {
	"supplier_reference": "invoice number",
	"posting_date": "invoice date",
	"due_date": "due date",
	"sum": "total amount",
	"payment_reference": "payment reference",
}
NUMERIC = {"sum", "net_total", "total_taxes"}
DATES = {"posting_date", "due_date"}
DONE_STATUSES = ("Approved to Pay", "Sent to DATEV", "Paid")


def _same(field, ai_value, value):
	if field in NUMERIC:
		return abs(flt(ai_value) - flt(value)) < 0.01
	if field in DATES:
		try:
			return bool(ai_value) == bool(value) and (not value or getdate(ai_value) == getdate(value))
		except Exception:
			return cstr(ai_value) == cstr(value)
	return cstr(ai_value).strip().upper() == cstr(value).strip().upper()


def corrections_for(doc, run):
	"""[{field, ai_value, human_value}] for values the run set that differ now."""
	analysis = frappe.parse_json(run.analysis or "{}") or {}
	ai_values = ((analysis.get("extraction") or {}).get("values")) or {}
	fields_set = [f.strip() for f in cstr(run.fields_set).split(",") if f.strip()]
	result = []
	for field in fields_set:
		if field not in LEARNED_FIELDS or field not in ai_values:
			continue
		value = doc.get(field)
		if not _same(field, ai_values[field], value):
			result.append({"field": field, "ai_value": ai_values[field], "human_value": cstr(value) if value is not None else None})
	return result


def ai_user():
	return frappe.db.get_single_value("phamos Settings", "ai_accountant_user")


def collect(doc, user=None):
	"""After a person saved a receipt: record corrections on its latest run and suggest rules.
	`user` is who made the change (default: the session user)."""
	from phamos.ai_agents import feedback

	user = user or frappe.session.user
	if not doc.get("ai_run") or user == ai_user() or feedback.is_ai_user(user):
		return None
	run = frappe.get_doc("AI Agent Run", doc.ai_run)
	if run.status != "Completed":
		return None
	found = corrections_for(doc, run)
	for c in feedback.record(run, found, user, done=doc.status in DONE_STATUSES):
		suggest_rule(doc, run, c)
	return found


@frappe.whitelist(methods=["POST"])
def backfill(days=365):
	"""One-time: check receipts read by the AI in the last `days` for corrections made
	before this feature existed. The receipt's last editor counts as the one who corrected.
	Safe to run again (corrections already recorded are not counted twice)."""
	frappe.only_for(("System Manager", "Accounts Manager"))
	since = frappe.utils.add_days(frappe.utils.nowdate(), -cint(days))
	names = frappe.get_all("Accounting Receipt", filters={"ai_run": ("is", "set"), "modified": (">=", since)}, pluck="name")
	corrected = 0
	for name in names:
		doc = frappe.get_doc("Accounting Receipt", name)
		if collect(doc, user=doc.modified_by):
			corrected += 1
	return {"receipts": len(names), "corrected": corrected}


# --- suggested reading rules ----------------------------------------------------------------


def _variants(field, value):
	"""How a value may be written in the PDF text."""
	value = cstr(value).strip()
	if not value:
		return []
	if field in DATES:
		try:
			d = getdate(value)
		except Exception:
			return [value]
		return [d.strftime("%d.%m.%Y"), d.strftime("%d.%m.%y"), d.strftime("%Y-%m-%d"), d.strftime("%d/%m/%Y")]
	if field in NUMERIC:
		amount = flt(value)
		german = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
		return [german, german.replace(".", ""), f"{amount:.2f}"]
	return [value]


def label_before(text, field, value):
	"""The few words right before the value in the document text, e.g. 'Rechnungsnummer:'."""
	for variant in _variants(field, value):
		index = text.find(variant)
		if index <= 0:
			continue
		line_start = text.rfind("\n", 0, index) + 1
		before = text[line_start:index]
		before = re.sub(r"[|*_#`]+", " ", before).strip(" \t:-–|")
		words = before.split()
		label = " ".join(words[-3:]).strip(" :")
		if label and not re.fullmatch(r"[\d.,\s€$%-]+", label):
			return label[:60]
	return None


def suggest_rule(doc, run, correction):
	"""Create or count a suggested Extract skill for this supplier and field."""
	field = correction["field"]
	if field not in RULE_FIELDS or not doc.supplier:
		return None
	key = f"{doc.supplier}::{field}"
	from phamos.ai_agents import feedback

	return feedback.suggestion(key, run, lambda: _rule_skill(doc, run, correction))


def _rule_skill(doc, run, correction):
	field = correction["field"]
	text = cstr(doc.get("ai_document_text"))
	human_label = label_before(text, field, correction["human_value"]) if text else None
	ai_label = label_before(text, field, correction["ai_value"]) if text else None
	what = _(RULE_FIELDS[field])
	supplier_name = doc.get("supplier_name") or doc.supplier
	if human_label and ai_label and human_label != ai_label:
		action = _("The {0} is the value after \"{1}\", not the one after \"{2}\".").format(what, human_label, ai_label)
	elif human_label:
		action = _("The {0} is the value after \"{1}\".").format(what, human_label)
	else:
		action = _("Read the {0} carefully: on {1} documents it was read as \"{2}\" but is \"{3}\".").format(
			what, supplier_name, correction["ai_value"], correction["human_value"])
	user = frappe.utils.get_fullname(correction.get("user") or frappe.session.user)
	return {
		"skill_name": _("Read {0}: {1}").format(supplier_name, what)[:140],
		"phase": "Extract",
		"order": 50,
		"party_doctype": "Supplier",
		"party": doc.supplier,
		"on_fail": "Continue",
		"description": _("Suggested after {0} corrected the {1} on {2}.").format(user, what, doc.name),
		"prompt_rules": [
			{
				"enabled": 1,
				"order": 1,
				"case_description": _("Documents from {0}").format(supplier_name),
				"action": action,
				"reason": _("{0} corrected \"{1}\" to \"{2}\" on {3} ({4}).").format(
					user, correction["ai_value"], correction["human_value"], doc.name, run.name),
			}
		],
	}


def accept_suggestion(name):
	from phamos.ai_agents import feedback

	return feedback.accept_suggestion(name)


def dismiss_suggestion(name):
	from phamos.ai_agents import feedback

	return feedback.dismiss_suggestion(name)
