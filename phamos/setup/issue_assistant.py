# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Setup for the phamos Issue Assistant (#2111): role, user, Raven bot, AI Agent, settings and the
Customer's "AI processing allowed" switch.

Called from after_migrate. Idempotent: every step checks before it creates. The assistant stays off
(Issue Assistant Settings.enabled) until someone switches it on.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.permissions import add_permission, update_permission_property

ASSISTANT_NAME = "phamos Issue Assistant"
ASSISTANT_ROLE = "Issue Assistant"
ASSISTANT_EMAIL = "issue-assistant@phamos.eu"
SETTINGS = "Issue Assistant Settings"
HANDLERS = "phamos.ai_agents.agents.issue"
GATE_SKILL_NAME = "Check AI gate"
CLASSIFY_SKILL_NAME = "Classify with AI model"
CUSTOMER_SECTION = "custom_implementation_specific"
AI_ALLOWED_FIELD = "custom_ai_processing_allowed"

# Pages whose reports never go to the model until #1904 decides on HR and salary data. Only the
# ones that exist on the site are stored (HRMS may be missing).
DEFAULT_EXCLUDED_DOCTYPES = (
	"Leave Application",
	"Leave Allocation",
	"Attendance",
	"Employee",
	"Salary Slip",
	"Salary Structure Assignment",
	"Payroll Entry",
	"Employee Grievance",
	"Appraisal",
)

# What the assistant's role may do. No delete anywhere, nothing from HR or accounting.
ROLE_RIGHTS = {
	"Issue": ("read", "write", "create", "report"),
	"Customer": ("read",),
	"Contact": ("read", "create"),
	"Lead": ("read",),
	"Implementation": ("read",),
	"Project": ("read",),
	"Employee": ("read",),
	"Issue Type": ("read",),
	"Issue Priority": ("read",),
	"GitLab Issue": ("read",),
}

CUSTOMER_FIELDS = [
	{
		"fieldname": CUSTOMER_SECTION,
		"label": "Implementation Specific",
		"fieldtype": "Section Break",
		"insert_after": "",
		"collapsible": 0,
	},
	{
		"fieldname": AI_ALLOWED_FIELD,
		"label": "AI processing allowed",
		"fieldtype": "Check",
		"default": "0",
		"insert_after": CUSTOMER_SECTION,
		"description": "Set only once this customer's AVV lists Mistral as sub-processor (#2110). Until then the "
		"Issue Assistant sends none of this customer's Issues to the AI model.",
	},
]


def after_migrate():
	ensure_role()
	user = ensure_user()
	bot = ensure_raven_bot()
	ensure_settings(user)
	ensure_agent(user, bot)
	ensure_classify_skill()
	ensure_customer_fields()


def ensure_role():
	if not frappe.db.exists("Role", ASSISTANT_ROLE):
		frappe.get_doc(
			{"doctype": "Role", "role_name": ASSISTANT_ROLE, "desk_access": 1, "is_custom": 1}
		).insert(ignore_permissions=True)
	for doctype, rights in ROLE_RIGHTS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		if not _has_role_rule(doctype):
			# the first custom rule copies the doctype's standard rules into Custom DocPerm
			add_permission(doctype, ASSISTANT_ROLE, permlevel=0, ptype="read")
		for ptype in rights:
			update_permission_property(doctype, ASSISTANT_ROLE, 0, ptype, 1, validate=False)


def _has_role_rule(doctype):
	filters = {"parent": doctype, "role": ASSISTANT_ROLE, "permlevel": 0}
	return frappe.db.exists("Custom DocPerm", filters) or frappe.db.exists("DocPerm", filters)


def ensure_user():
	"""The assistant's user. No password, so nobody can log in as it; runs switch to it, so the
	document history shows what the assistant set and what a human changed afterwards."""
	configured = frappe.db.get_single_value(SETTINGS, "assistant_user")
	if configured and frappe.db.exists("User", configured):
		return configured
	if frappe.db.exists("User", ASSISTANT_EMAIL):
		return ASSISTANT_EMAIL
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": ASSISTANT_EMAIL,
			"first_name": ASSISTANT_NAME,
			"user_type": "System User",
			"send_welcome_email": 0,
			"roles": [{"role": ASSISTANT_ROLE}],
		}
	)
	user.flags.no_welcome_mail = True
	user.insert(ignore_permissions=True)
	return user.name


def ensure_raven_bot():
	"""The bot that posts the assistant's brief in the Issue chat. None without Raven."""
	if "raven" not in frappe.get_installed_apps():
		return None
	if not frappe.db.exists("Raven Bot", ASSISTANT_NAME):
		frappe.get_doc(
			{
				"doctype": "Raven Bot",
				"bot_name": ASSISTANT_NAME,
				"description": "First point of contact for new Issues: posts what it found in the Issue chat.",
			}
		).insert(ignore_permissions=True)
	return ASSISTANT_NAME


def ensure_settings(user):
	settings = frappe.get_single(SETTINGS)
	if settings.assistant_user:
		return
	# first setup only: a list someone emptied later stays empty
	settings.assistant_user = user
	for doctype in DEFAULT_EXCLUDED_DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			settings.append("excluded_doctypes", {"excluded_doctype": doctype})
	settings.flags.ignore_permissions = True
	settings.save()


def ensure_agent(user, bot):
	if not frappe.db.exists("AI Agent", ASSISTANT_NAME):
		frappe.get_doc(
			{
				"doctype": "AI Agent",
				"agent_name": ASSISTANT_NAME,
				"enabled": 1,
				"applies_to_doctype": "Issue",
				"handler_module": HANDLERS,
				"user": user,
				"raven_bot": bot,
				"run_on_insert": 1,
				"description": "First point of contact for new Issues (#1953).",
			}
		).insert(ignore_permissions=True)
	if not frappe.db.exists("AI Skill", {"agent": ASSISTANT_NAME, "handler": "check_gate"}):
		frappe.get_doc(
			{
				"doctype": "AI Skill",
				"skill_name": GATE_SKILL_NAME,
				"agent": ASSISTANT_NAME,
				"enabled": 1,
				"phase": "Extract",
				"order": 10,
				"handler": "check_gate",
				# fail closed: without a gate decision no later skill (the model, #2113) may run
				"on_fail": "Stop Run",
				"description": "Assigns the assistant and a Desk-user reporter, and decides whether the Issue may go to "
				"the AI model: sensitive page, the Customer's \"AI processing allowed\", internal or unknown sender.",
			}
		).insert(ignore_permissions=True)


def ensure_classify_skill():
	"""The model's step (#2113). Runs only when the gate allowed it (checked in the handler too)."""
	if frappe.db.exists("AI Skill", {"agent": ASSISTANT_NAME, "handler": "classify"}):
		return
	frappe.get_doc(
		{
			"doctype": "AI Skill",
			"skill_name": CLASSIFY_SKILL_NAME,
			"agent": ASSISTANT_NAME,
			"enabled": 1,
			"phase": "Classify",
			"order": 10,
			"handler": "classify",
			"gate_on_previous": 1,
			"on_fail": "Continue",
			"description": "The AI model reads the Issue (text and Phriend screenshot) and picks Issue Type, Priority "
			"and a person from lists built in code; writes only empty fields on strong confidence, never the "
			"reporter's priority; assigns the person itself only on strong confidence and priority High.",
		}
	).insert(ignore_permissions=True)


def ensure_customer_fields():
	if frappe.get_meta("Customer").has_field(AI_ALLOWED_FIELD):
		return
	create_custom_fields({"Customer": [{**f, "module": "AI Agents"} for f in CUSTOMER_FIELDS]}, update=False)

