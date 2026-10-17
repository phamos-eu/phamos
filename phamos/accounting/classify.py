# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Propose the expense account of each receipt line.

Order, first answer that is sure enough wins:
1. the assignment library (exact or similar descriptions, this supplier first),
2. the supplier's usual account,
3. Mistral, choosing only among the accounts offered to the AI.

A line nobody is sure about keeps an empty account, gets up to three candidates and an
"account_unclear" flag, so a person decides instead of the AI guessing. Only lines without
an account are touched; a person's choice is never replaced.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from phamos.accounting import library
from phamos.accounting.expense_accounts import ai_expense_accounts
from phamos.ai_agents import llm
from phamos.ai_agents.context import PASSED, UNCERTAIN, SkillResult

DEFAULT_PARAMS = {
	"match_score": library.MATCH_SCORE,
	"auto_apply_score": library.AUTO_APPLY_SCORE,
	"use_llm": 1,
	"llm_min_confidence": 80,
	"max_llm_lines": 30,
}
LLM_MAX_CONFIDENCE = 90

# What the cockpit's skill editor shows for this skill's params.
PARAM_FIELDS = [
	{"key": "auto_apply_score", "label": "Assign at score", "type": "int", "min": 50, "max": 100,
		"help": "A library match at or above this score sets the account without asking."},
	{"key": "match_score", "label": "Similar description from", "type": "int", "min": 50, "max": 100,
		"help": "How similar (0-100) a description must be to count as a library match."},
	{"key": "use_llm", "label": "Ask Mistral when the library has no answer", "type": "check"},
	{"key": "llm_min_confidence", "label": "Accept Mistral from", "type": "int", "min": 0, "max": 100,
		"help": "Mistral's own confidence (%) needed before its account is set."},
	{"key": "max_llm_lines", "label": "Lines per Mistral call", "type": "int", "min": 1, "max": 100},
]


def params_of(skill=None):
	params = dict(DEFAULT_PARAMS)
	raw = skill.get("params") if skill else None
	if raw:
		params.update(json.loads(raw) if isinstance(raw, str) else raw)
	return params


def run_classify_skill(ctx, skill):
	"""Propose the expense account of every line that has none yet."""
	result = classify_receipt(ctx.doc, params_of(skill), model=ctx.agent.llm_model or None)
	ctx.llm_calls += result["llm_calls"]
	if result["llm_model"]:
		ctx.llm_model = result["llm_model"]
	ctx.analysis["classification"] = result["lines"]
	status = UNCERTAIN if result["unclear"] else PASSED
	return SkillResult(
		status,
		confidence=result["confidence"],
		fields_set=["items"] if result["assigned"] else [],
		flags=result["flags"],
		message=_("{0} of {1} lines assigned, {2} unclear").format(result["assigned"], result["open"], result["unclear"]),
		output={"assigned": result["assigned"], "unclear": result["unclear"]},
	)


def classify_receipt(doc, params=None, model=None, save=True):
	"""Fill the expense account of open lines. Returns a summary with per-line reasons."""
	params = params or dict(DEFAULT_PARAMS)
	company = doc.company or frappe.defaults.get_global_default("company")
	entries = library.entries(company)
	open_rows = [row for row in doc.get("items") or [] if not row.expense_account and cstr(row.item_name).strip()]
	report, pending = {}, []

	for row in open_rows:
		candidates = library.find(row.item_name, doc.supplier, company, params["match_score"], entries)
		top = candidates[0] if candidates else None
		if top and top["score"] >= params["auto_apply_score"]:
			_assign(row, top["account"], top["source"], top["score"], top["reason"], entry=top.get("entry"),
				cost_center=top.get("cost_center"))
			report[row.name] = _line_report(row, top["source"], top["score"], top["reason"], candidates)
		else:
			pending.append((row, candidates))

	llm_calls, llm_model = 0, None
	if pending and cint(params["use_llm"]):
		answers, llm_model, error = _ask_llm(doc, company, pending[: cint(params["max_llm_lines"])], model)
		llm_calls = 0 if error else 1
		still_open = []
		for index, (row, candidates) in enumerate(pending, 1):
			answer = answers.get(index)
			if answer and answer["confidence"] >= params["llm_min_confidence"]:
				score = min(answer["confidence"], LLM_MAX_CONFIDENCE)
				entry = library.learn(company, doc.supplier, row.item_name, answer["account"], validation="AI",
					origin="AI", receipt=doc.name, hits=0)
				_assign(row, answer["account"], "AI", score, answer["reason"], entry=entry)
				report[row.name] = _line_report(row, "AI", score, answer["reason"], candidates)
			else:
				if answer:
					candidates = candidates + [{"account": answer["account"], "score": answer["confidence"], "source": "AI",
						"reason": answer["reason"]}]
				still_open.append((row, candidates, error or (answer and answer["reason"]) or ""))
		pending = still_open
	else:
		pending = [(row, candidates, "") for row, candidates in pending]

	flags = []
	for row, candidates, note in pending:
		shortlist = _shortlist(candidates)
		row.ai_candidates = json.dumps(shortlist) if shortlist else None
		row.ai_reason = note or (_("No library entry or AI answer was sure enough.") if not shortlist else _("Not sure: pick one of the candidates."))
		row.ai_confidence = shortlist[0]["score"] if shortlist else 0
		report[row.name] = _line_report(row, None, row.ai_confidence, row.ai_reason, candidates)
		flags.append({"code": "account_unclear", "severity": "warn", "field": "items",
			"message": _("Which expense account fits \"{0}\"?").format(row.item_name)})

	assigned = len(open_rows) - len(pending)
	if save and open_rows:
		doc.save(ignore_version=False)
	scores = [r["score"] for r in report.values()]
	return {
		"open": len(open_rows),
		"assigned": assigned,
		"unclear": len(pending),
		"confidence": min(scores) if scores else None,
		"flags": flags,
		"lines": list(report.values()),
		"llm_calls": llm_calls,
		"llm_model": llm_model,
	}


def _assign(row, account, source, score, reason, entry=None, cost_center=None):
	row.expense_account = account
	row.ai_expense_account = account
	row.assignment_source = source
	row.assignment = entry
	row.ai_confidence = score
	row.ai_reason = reason
	row.ai_candidates = None
	if cost_center and not row.cost_center:
		row.cost_center = cost_center


def _shortlist(candidates):
	seen, result = set(), []
	for c in sorted(candidates, key=lambda c: -flt(c["score"])):
		if c["account"] in seen:
			continue
		seen.add(c["account"])
		result.append({"account": c["account"], "score": round(flt(c["score"])), "source": c["source"], "reason": c.get("reason") or ""})
		if len(result) == 3:
			break
	return result


def _line_report(row, source, score, reason, candidates):
	return {
		"row": row.name,
		"description": row.item_name,
		"pattern": library.normalize_description(row.item_name),
		"account": row.expense_account,
		"source": source,
		"score": score,
		"reason": reason,
		"candidates": _shortlist(candidates),
	}


# --- Mistral -------------------------------------------------------------------------------


def build_prompt(doc, accounts, pending):
	account_lines = [
		f'- {a["account_number"]} {a["account_name"]}' + (f' (e.g. {", ".join(a["keywords"][:12])})' if a["keywords"] else "")
		for a in accounts
	]
	lines = []
	for index, (row, candidates) in enumerate(pending, 1):
		hint = ""
		if candidates:
			hint = "; earlier similar lines: " + ", ".join(
				f'{frappe.db.get_value("Account", c["account"], "account_number") or c["account"]} ({c["source"]})' for c in candidates[:3]
			)
		lines.append(f'{index}. "{row.item_name}" amount {flt(row.amount)} tax {flt(row.tax_rate)} %{hint}')
	supplier = doc.supplier_name if doc.get("supplier_name") else doc.supplier
	return "\n".join(
		[
			"Assign each invoice line of this purchase receipt to one expense account from the list.",
			"Use only account numbers from the list. If no account clearly fits, answer \"none_fits\".",
			"Do not guess: a confidence below 0.8 means a person will decide.",
			f"Supplier: {supplier or 'unknown'}. Receipt type: {doc.receipt_type or 'unknown'}. Title: {doc.title or ''}",
			"",
			"Accounts:",
			*account_lines,
			"",
			"Lines:",
			*lines,
			"",
			'Answer as JSON: {"lines": [{"index": 1, "account_number": "6805" or "none_fits", "confidence": 0.0-1.0, '
			'"reason": "one short sentence"}]}',
		]
	)


def _ask_llm(doc, company, pending, model):
	"""{index: {account, confidence (0-100), reason}}, model, error message."""
	accounts = ai_expense_accounts(company)
	if not accounts:
		return {}, None, _("No accounts are offered to the AI yet (Account > Offered to the AI).")
	try:
		answer, used_model = llm.chat_json(
			build_prompt(doc, accounts, pending),
			model=model,
			system="You are a careful German bookkeeper (SKR04). You only answer with JSON.",
		)
	except llm.LLMNotConfigured:
		return {}, None, _("Mistral is not configured, so only the library was used.")
	except Exception as e:
		frappe.log_error(title=_("Account proposal for {0} failed").format(doc.name), message=frappe.get_traceback())
		return {}, None, _("The AI could not be asked: {0}").format(cstr(e)[:200])
	by_number = {a["account_number"]: a["account"] for a in accounts if a["account_number"]}
	result = {}
	for line in (answer or {}).get("lines") or []:
		if not isinstance(line, dict):
			continue
		number = cstr(line.get("account_number")).strip()
		if number not in by_number:
			continue
		try:
			confidence = max(0.0, min(1.0, float(line.get("confidence") or 0))) * 100
		except (TypeError, ValueError):
			confidence = 0
		result[cint(line.get("index"))] = {
			"account": by_number[number],
			"confidence": round(confidence),
			"reason": _("AI: {0}").format(cstr(line.get("reason")).strip()[:200] or number),
		}
	return result, used_model, None


@frappe.whitelist(methods=["POST"])
def suggest_accounts(name):
	"""Cockpit button: propose accounts for the open lines of one receipt now, as the AI user."""
	from phamos.ai_agents.runner import get_agent

	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("write")
	agent = get_agent("Accounting Receipt")
	skill = frappe.db.get_value("AI Skill", {"agent": agent.name, "handler": "classify_lines"}, ["name", "params"], as_dict=True) if agent else None
	previous = frappe.session.user
	try:
		if agent and agent.user:
			frappe.set_user(agent.user)
		doc = frappe.get_doc("Accounting Receipt", name)
		result = classify_receipt(doc, params_of(skill), model=agent.llm_model if agent else None)
	finally:
		frappe.set_user(previous)
	from phamos.api.accounting_spa import get_receipt

	return {"result": {k: result[k] for k in ("open", "assigned", "unclear")}, "receipt": get_receipt(name)}
