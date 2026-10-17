# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Skill handlers of the AI Accountant (agent "Accounting Agent" on Accounting Receipt)."""

from phamos.accounting.classify import run_classify_skill
from phamos.accounting.decide import run_decide_skill
from phamos.accounting.extraction import run_extract_skill

SKILLS = {
	"extract_document": run_extract_skill,
	"classify_lines": run_classify_skill,
	"decide_receipt": run_decide_skill,
}


def _param_fields():
	from phamos.accounting import classify, decide

	return {
		"classify_lines": (classify.PARAM_FIELDS, classify.DEFAULT_PARAMS),
		"decide_receipt": (decide.PARAM_FIELDS, decide.DEFAULT_PARAMS),
	}


def param_fields(handler):
	"""(fields, defaults) the cockpit's skill editor shows for a handler's params."""
	return _param_fields().get(handler, ([], {}))


def dry_run(handler, doc, params, prompt_rules):
	"""What the skill would do on this receipt with these settings; writes nothing."""
	from phamos.accounting import dry_run as runs

	return runs.dry_run(handler, doc, params, prompt_rules)


def get_party(doc):
	return ("Supplier", doc.supplier) if doc.get("supplier") else None


def finalize(ctx):
	"""Mirror the run's result onto the receipt for lists and the cockpit."""
	ctx.doc.db_set(
		{"ai_run": ctx.run.name, "ai_summary": ctx.summary or None, "ai_confidence": ctx.confidence or 0},
		update_modified=False,
	)
