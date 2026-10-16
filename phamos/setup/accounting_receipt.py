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


def ensure_accounting_receipt_setup():
	"""Create the role, the AI user, its Raven bot and the Issue link field."""
	ensure_role()
	user = ensure_ai_user()
	ensure_raven_bot()
	_remember_ai_user(user)
	ensure_issue_accounting_receipt_field()


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
