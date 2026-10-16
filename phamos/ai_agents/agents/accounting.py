# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Skill handlers of the AI Accountant (agent "Accounting Agent" on Accounting Receipt)."""

from phamos.accounting.extraction import run_extract_skill

SKILLS = {
	"extract_document": run_extract_skill,
}


def get_party(doc):
	return ("Supplier", doc.supplier) if doc.get("supplier") else None


def finalize(ctx):
	"""Mirror the run's result onto the receipt for lists and the cockpit."""
	ctx.doc.db_set(
		{"ai_run": ctx.run.name, "ai_summary": ctx.summary or None, "ai_confidence": ctx.confidence or 0},
		update_modified=False,
	)
