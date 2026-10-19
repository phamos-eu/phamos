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
from frappe.utils import cint, cstr, flt, getdate, now_datetime

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
	user = user or frappe.session.user
	if not doc.get("ai_run") or user == ai_user():
		return None
	run = frappe.get_doc("AI Agent Run", doc.ai_run)
	if run.status != "Completed":
		return None
	found = corrections_for(doc, run)
	previous = {c["field"]: c for c in frappe.parse_json(run.corrections or "[]") or []}
	now = now_datetime()
	for c in found:
		old = previous.get(c["field"])
		c["user"] = old["user"] if old and old.get("human_value") == c["human_value"] else user
		c["at"] = old["at"] if old and old.get("human_value") == c["human_value"] else str(now)
	new = [c for c in found if c["field"] not in previous or previous[c["field"]].get("human_value") != c["human_value"]]
	values = {"corrections": frappe.as_json(found) if found else None, "feedback_collected_at": now}
	if found:
		values.update(outcome="Corrected", corrected_by=user)
	elif doc.status in DONE_STATUSES:
		values["outcome"] = "Accepted"
	else:
		values["outcome"] = None
	run.db_set(values, update_modified=False)
	for c in new:
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
	existing = frappe.db.get_value("AI Skill", {"suggestion_key": key}, ["name", "dismissed", "occurrences", "origin"], as_dict=True)
	if existing:
		if not existing.dismissed and existing.origin == "Suggested":
			frappe.db.set_value("AI Skill", existing.name, {"occurrences": (existing.occurrences or 0) + 1, "source_run": run.name})
		return existing.name

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
	agent = frappe.db.get_value("AI Agent Run", run.name, "agent")
	skill = frappe.get_doc(
		{
			"doctype": "AI Skill",
			"skill_name": _("Read {0}: {1}").format(supplier_name, what)[:140],
			"agent": agent,
			"enabled": 0,
			"phase": "Extract",
			"order": 50,
			"origin": "Suggested",
			"party_doctype": "Supplier",
			"party": doc.supplier,
			"on_fail": "Continue",
			"occurrences": 1,
			"source_run": run.name,
			"suggestion_key": key,
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
	)
	skill.insert(ignore_permissions=True)
	return skill.name


def accept_suggestion(name):
	skill = frappe.get_doc("AI Skill", name)
	skill.check_permission("write")
	if skill.origin != "Suggested":
		frappe.throw(_("{0} is not a suggestion.").format(name))
	skill.enabled = 1
	skill.origin = "Learned"
	skill.dismissed = 0
	skill.save()
	return skill.name


def dismiss_suggestion(name):
	skill = frappe.get_doc("AI Skill", name)
	skill.check_permission("write")
	if skill.origin != "Suggested":
		frappe.throw(_("{0} is not a suggestion.").format(name))
	skill.dismissed = 1
	skill.enabled = 0
	skill.save()
	return skill.name
