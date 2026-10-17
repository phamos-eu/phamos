# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Try an AI skill's settings on one receipt without saving anything.

- Read receipt: shows the prompt Mistral would get (no call, so no cost).
- Propose expense accounts: the library's answer per open line (Mistral is not asked).
- Decide next step: the decision and flags with the draft thresholds.
"""

import copy

import frappe
from frappe import _


def _latest_extraction(doc):
	from phamos.ai_agents.runner import latest_run

	run = latest_run("Accounting Receipt", doc.name)
	analysis = frappe.parse_json(frappe.db.get_value("AI Agent Run", run, "analysis") or "{}") if run else {}
	return (analysis or {}).get("extraction") or {}


def dry_run(handler, doc, params, prompt_rules):
	if handler == "extract_document":
		from phamos.accounting.extraction import build_prompt

		rules = [frappe._dict(r) for r in prompt_rules or [] if r.get("enabled", 1)]
		text = doc.get("ai_document_text") or _("(The PDF has not been read yet; its text would appear here.)")
		return {"kind": "prompt", "prompt": build_prompt(text, rules, doc.company)}

	if handler == "classify_lines":
		from phamos.accounting.classify import DEFAULT_PARAMS, classify_receipt

		trial = copy.deepcopy(doc)
		result = classify_receipt(trial, {**DEFAULT_PARAMS, **(params or {}), "use_llm": 0}, save=False)
		return {
			"kind": "classify",
			"open": result["open"],
			"assigned": result["assigned"],
			"unclear": result["unclear"],
			"lines": result["lines"],
			"note": _("Mistral is not asked in a dry run; lines it would get are shown as unclear."),
		}

	if handler == "decide_receipt":
		from phamos.accounting.decide import DEFAULT_PARAMS, evaluate

		result = evaluate(doc, {**DEFAULT_PARAMS, **(params or {})}, extraction=_latest_extraction(doc))
		return {"kind": "decide", **{k: result[k] for k in ("decision", "confidence", "flags", "summary", "paid")},
			"history_count": result["history"]["count"]}

	return {"kind": "none", "note": _("This skill has no dry run.")}
