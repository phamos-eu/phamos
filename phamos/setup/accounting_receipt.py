# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Setup for the Accounting Receipt inbox and its AI Accountant.

Called from after_migrate. Idempotent: every step checks before it creates.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

AI_ACCOUNTANT_ROLE = "AI Accountant"
AI_ACCOUNTANT_EMAIL = "ai-accountant@phamos.eu"
AI_ACCOUNTANT_NAME = "AI Accountant"
SETTINGS_DOCTYPE = "phamos Settings"
ACCOUNTING_AGENT = "Accounting Agent"
ACCOUNTING_HANDLERS = "phamos.ai_agents.agents.accounting"
EXTRACT_SKILL_NAME = "Read receipt"
CLASSIFY_SKILL_NAME = "Propose expense accounts"


def ensure_accounting_receipt_setup():
	"""Create the role, the AI user, its Raven bot, the Accounting Agent and the Issue link field."""
	ensure_role()
	user = ensure_ai_user()
	ensure_raven_bot()
	_remember_ai_user(user)
	ensure_accounting_agent()
	ensure_issue_accounting_receipt_field()
	from phamos.accounting.expense_accounts import ensure_expense_account_setup

	ensure_expense_account_setup()


def ensure_accounting_agent():
	"""The AI Accountant as an AI Agent with its first skill: reading the receipt PDF."""
	if not frappe.db.exists("AI Agent", ACCOUNTING_AGENT):
		frappe.get_doc(
			{
				"doctype": "AI Agent",
				"agent_name": ACCOUNTING_AGENT,
				"enabled": 1,
				"applies_to_doctype": "Accounting Receipt",
				"handler_module": ACCOUNTING_HANDLERS,
				"user": frappe.db.get_single_value(SETTINGS_DOCTYPE, "ai_accountant_user") or AI_ACCOUNTANT_EMAIL,
				"raven_bot": AI_ACCOUNTANT_NAME if frappe.db.exists("Raven Bot", AI_ACCOUNTANT_NAME) else None,
				"run_on_insert": 1,
				"run_on_fields": "attachment",
				"description": "Reads incoming receipts and prepares them for the accounting team.",
			}
		).insert(ignore_permissions=True)
	ensure_classify_skill()
	return ensure_extract_skill()


def ensure_extract_skill():
	"""Name of the agent's general (not supplier specific) PDF reading skill."""
	existing = frappe.db.get_value(
		"AI Skill", {"agent": ACCOUNTING_AGENT, "handler": "extract_document", "party": ("is", "not set")}, "name"
	)
	if existing:
		return existing
	skill = frappe.get_doc(
		{
			"doctype": "AI Skill",
			"skill_name": EXTRACT_SKILL_NAME,
			"agent": ACCOUNTING_AGENT,
			"enabled": 1,
			"phase": "Extract",
			"order": 10,
			"handler": "extract_document",
			"on_fail": "Stop Run",
			"description": "Reads the PDF with Mistral and fills empty fields of the receipt, including item lines.",
		}
	).insert(ignore_permissions=True)
	return skill.name


def ensure_classify_skill():
	"""The general skill that proposes each line's expense account (library first, then Mistral)."""
	existing = frappe.db.get_value(
		"AI Skill", {"agent": ACCOUNTING_AGENT, "handler": "classify_lines", "party": ("is", "not set")}, "name"
	)
	if existing:
		return existing
	from phamos.accounting.classify import DEFAULT_PARAMS

	return frappe.get_doc(
		{
			"doctype": "AI Skill",
			"skill_name": CLASSIFY_SKILL_NAME,
			"agent": ACCOUNTING_AGENT,
			"enabled": 1,
			"phase": "Classify",
			"order": 10,
			"handler": "classify_lines",
			"on_fail": "Continue",
			"params": frappe.as_json(DEFAULT_PARAMS),
			"description": "Proposes the expense account of each line without one: the assignment library first, then the "
			"supplier's usual account, then Mistral choosing among the accounts offered to the AI. Unsure lines stay "
			"empty with candidates for a person.",
		}
	).insert(ignore_permissions=True).name


def ensure_role():
	if frappe.db.exists("Role", AI_ACCOUNTANT_ROLE):
		return
	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": AI_ACCOUNTANT_ROLE,
			"desk_access": 1,
			"is_custom": 1,
		}
	).insert(ignore_permissions=True)


def ensure_ai_user():
	"""Return the AI Accountant user, creating it when no user is configured yet.

	The user has no password, so nobody can log in as it. Background jobs switch to it
	so the document history shows which values the AI set and which a human corrected.
	"""
	configured = frappe.db.get_single_value(SETTINGS_DOCTYPE, "ai_accountant_user")
	if configured and frappe.db.exists("User", configured):
		return configured
	if frappe.db.exists("User", AI_ACCOUNTANT_EMAIL):
		return AI_ACCOUNTANT_EMAIL

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": AI_ACCOUNTANT_EMAIL,
			"first_name": AI_ACCOUNTANT_NAME,
			"user_type": "System User",
			"send_welcome_email": 0,
			"roles": [{"role": AI_ACCOUNTANT_ROLE}, {"role": "Accounts User"}],
		}
	)
	user.flags.no_welcome_mail = True
	user.insert(ignore_permissions=True)
	return user.name


def ensure_raven_bot():
	"""Create the Raven bot the AI Accountant uses to ask humans. Saving it creates its Raven User."""
	if "raven" not in frappe.get_installed_apps():
		return
	if frappe.db.exists("Raven Bot", AI_ACCOUNTANT_NAME):
		return
	frappe.get_doc(
		{
			"doctype": "Raven Bot",
			"bot_name": AI_ACCOUNTANT_NAME,
			"description": "Asks the accounting team about receipts it cannot decide alone.",
		}
	).insert(ignore_permissions=True)


def _remember_ai_user(user):
	if user and not frappe.db.get_single_value(SETTINGS_DOCTYPE, "ai_accountant_user"):
		frappe.db.set_single_value(SETTINGS_DOCTYPE, "ai_accountant_user", user)


def ensure_issue_accounting_receipt_field():
	"""Issue → Accounting Receipt link set by make_accounting_receipt and read by issue.js."""
	if frappe.get_meta("Issue").has_field("accounting_receipt"):
		return
	create_custom_fields(
		{
			"Issue": [
				{
					"fieldname": "accounting_receipt",
					"label": "Accounting Receipt",
					"fieldtype": "Link",
					"options": "Accounting Receipt",
					"insert_after": "customer",
					"read_only": 1,
					"no_copy": 1,
					"module": "Phamos",
				}
			]
		},
		update=False,
	)
