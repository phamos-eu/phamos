"""Move the extraction rules of the single AI Prompt Configuration onto the AI Skill
"Read receipt" of the Accounting Agent (#1020).

Runs once; a skill that already has rules is left alone. The old single doctype stays
readable for now and is retired once the cockpit has its skills page.
"""

import frappe

from phamos.setup.accounting_receipt import ensure_accounting_receipt_setup, ensure_extract_skill

RULE_FIELDS = ("enabled", "order", "case_description", "action", "reason")


def execute():
	ensure_accounting_receipt_setup()
	skill = frappe.get_doc("AI Skill", ensure_extract_skill())
	if skill.get("prompt_rules"):
		return
	rows = frappe.get_all(
		"AI Prompt Rule",
		filters={"parenttype": "AI Prompt Configuration", "parent": "AI Prompt Configuration"},
		fields=list(RULE_FIELDS),
		order_by="idx asc",
	)
	if not rows:
		return
	for row in rows:
		skill.append("prompt_rules", {field: row.get(field) for field in RULE_FIELDS})
	skill.save(ignore_permissions=True)
