# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The phamos Issue Assistant (AI Agent on Issue, #1953): first point of contact for new Issues.

Part one (#2111): intake. A new Issue in scope gets a run in the background. The run assigns the
assistant and a Desk-user reporter, decides in code whether the Issue may go to the AI model (the
gate), and posts a brief in the Issue chat. Identifying the sender (#2112) and the model's own work
(#2113) build on this.
"""

import frappe
from frappe import _
from frappe.utils import escape_html

from phamos.ai_agents.context import PASSED, SkillResult

SETTINGS = "Issue Assistant Settings"
AI_ALLOWED_FIELD = "custom_ai_processing_allowed"

# gate reasons, kept on the run (run_flags / analysis) and shown in the brief
SENSITIVE_PAGE = "sensitive_page"
CUSTOMER_ALLOWED = "customer_allowed"
CUSTOMER_NOT_ALLOWED = "customer_not_allowed"
INTERNAL = "internal"
UNKNOWN_SENDER = "unknown_sender"


def on_issue_insert(doc, method=None):
	"""Issue after_insert: queue the assistant's run for a new Issue in scope.

	Never blocks creating the Issue: a failure is logged and the Issue stays as it was.
	"""
	try:
		settings = frappe.get_cached_doc(SETTINGS)
		if not settings.enabled or not in_scope(doc, settings):
			return
		from phamos.ai_agents import runner

		runner.enqueue_run("Issue", doc.name, trigger="Insert")
	except Exception:
		frappe.log_error(title=f"Issue Assistant: could not queue {doc.name}")


def in_scope(doc, settings):
	"""Empty project or type lists mean all projects or types."""
	projects = {row.project for row in settings.scope_projects}
	if projects and doc.project not in projects:
		return False
	types = {row.issue_type for row in settings.scope_issue_types}
	return not types or doc.issue_type in types


def reporter_user(doc):
	"""The enabled User behind the Issue's reporter, or None."""
	user = doc.get("phriend_reported_by")
	if not user and doc.raised_by:
		user = frappe.db.get_value("User", {"name": doc.raised_by.strip()}, "name") or frappe.db.get_value(
			"User", {"email": doc.raised_by.strip()}, "name"
		)
	if not user or user in ("Guest", "Administrator"):
		return None
	return user if frappe.db.get_value("User", user, "enabled") else None


def logged_in_reporter(doc):
	"""The Desk user who created the Issue while logged in, or None.

	Only the Issue's `owner` counts: Frappe sets it from the session, so a caller cannot choose it.
	A Phriend report made on this system is inserted in the reporter's session, so its owner is the
	reporter. Fields a caller can send (`raised_by`, the From header of an e-mail, and
	`phriend_reported_by`) never make an Issue internal (AI review on !1314). E-mail Issues are
	inserted by the system (owner Administrator), and reports forwarded from another system
	(phriend_source_system) are vouched for by that system, not by us: neither counts.
	"""
	if doc.get("phriend_source_system"):
		return None
	user = doc.owner
	if not user or user in ("Guest", "Administrator"):
		return None
	if not frappe.db.get_value("User", user, "enabled"):
		return None
	return user if is_desk_user(user) else None


def is_desk_user(user):
	return bool(user) and frappe.db.get_value("User", user, "user_type") == "System User"


def customer_of(doc):
	"""The Customer the Issue belongs to: its own, else its Implementation's, else its Project's."""
	if doc.get("customer"):
		return doc.customer
	if doc.get("custom_implementation"):
		customer = frappe.db.get_value("Implementation", doc.custom_implementation, "customer")
		if customer:
			return customer
	if doc.get("project"):
		return frappe.db.get_value("Project", doc.project, "customer")
	return None


def model_allowed(doc, settings=None):
	"""Whether the Issue may go to the AI model, decided in code (#1953 decision 18).

	Returns {"allowed", "reason", "customer", "page"}. Order:
	1. a report from an excluded page (HR, salary, leave) never goes
	2. an Issue of a Customer goes only when that Customer has "AI processing allowed" (signed AVV)
	3. no Customer, reported by a phamos Desk user through a logged-in path: internal, goes
	4. no Customer, any other sender (also a staff address in an e-mail's From): does not go
	"""
	settings = settings or frappe.get_cached_doc(SETTINGS)
	page = doc.get("phriend_ref_doctype")
	excluded = {row.excluded_doctype for row in settings.excluded_doctypes}
	if page and page in excluded:
		return {"allowed": False, "reason": SENSITIVE_PAGE, "customer": None, "page": page}
	customer = customer_of(doc)
	if customer:
		allowed = bool(frappe.db.get_value("Customer", customer, AI_ALLOWED_FIELD))
		return {
			"allowed": allowed,
			"reason": CUSTOMER_ALLOWED if allowed else CUSTOMER_NOT_ALLOWED,
			"customer": customer,
			"page": page,
		}
	if logged_in_reporter(doc):
		return {"allowed": True, "reason": INTERNAL, "customer": None, "page": page}
	return {"allowed": False, "reason": UNKNOWN_SENDER, "customer": None, "page": page}


def assign(doc, assistant_user):
	"""The assistant owns the Issue; a reporter with a Desk login is assigned too. Existing open
	assignments (Phriend's own, a human's) are kept and not repeated. Returns the users added."""
	from frappe.desk.form.assign_to import add as assign_to

	users = [assistant_user]
	reporter = reporter_user(doc)
	if is_desk_user(reporter):
		users.append(reporter)
	added = []
	for user in dict.fromkeys(u for u in users if u):
		if frappe.db.exists(
			"ToDo", {"reference_type": "Issue", "reference_name": doc.name, "allocated_to": user, "status": "Open"}
		):
			continue
		assign_to({"assign_to": [user], "doctype": "Issue", "name": doc.name, "description": doc.subject})
		added.append(user)
	return added


def run_check_gate(ctx, skill):
	"""Skill "Check AI gate" (phase Extract): assignment and the gate."""
	assigned = assign(ctx.doc, ctx.agent.user)
	gate = model_allowed(ctx.doc)
	ctx.analysis["gate"] = gate
	ctx.analysis["assigned"] = assigned
	ctx.analysis["reporter"] = reporter_user(ctx.doc)
	ctx.flags.append({"code": f"gate_{gate['reason']}", "severity": "info", "message": gate_text(gate)})
	return SkillResult(status=PASSED, message=gate_text(gate), output={"gate": gate, "assigned": assigned})


SKILLS = {"check_gate": run_check_gate}


def get_party(doc):
	customer = customer_of(doc)
	return ("Customer", customer) if customer else None


def gate_text(gate):
	if gate["reason"] == SENSITIVE_PAGE:
		return _("AI model not used: reported from a sensitive page ({0}).").format(_(gate["page"]))
	if gate["reason"] == CUSTOMER_NOT_ALLOWED:
		return _("AI model not used: AI processing is not allowed for customer {0}.").format(gate["customer"])
	if gate["reason"] == UNKNOWN_SENDER:
		return _("AI model not used: the sender is not known as a customer or a phamos user.")
	if gate["reason"] == CUSTOMER_ALLOWED:
		return _("AI model may be used: customer {0} allows AI processing.").format(gate["customer"])
	return _("AI model may be used: internal Issue.")


def source_text(doc):
	if doc.get("phriend_source_system"):
		return _("Phriend report forwarded from {0}").format(doc.phriend_source_system)
	if doc.get("phriend_type"):
		return _("Phriend report")
	if doc.raised_by:
		return _("Email")
	return _("Created in ERPNext")


def sender_text(doc, reporter):
	name = doc.get("phriend_reported_by_name") or (frappe.utils.get_fullname(reporter) if reporter else "")
	email = doc.raised_by or ""
	label = " ".join(p for p in (name, f"<{email}>" if email and email != name else "") if p)
	return label or _("Unknown")


def brief_lines(ctx):
	# No gate result means the check failed: say so instead of deciding again here (fail closed).
	gate = ctx.analysis.get("gate")
	reporter = ctx.analysis.get("reporter")
	return [
		_("First look at {0}").format(ctx.doc.name),
		_("Sender: {0}").format(sender_text(ctx.doc, reporter)),
		_("Source: {0}").format(source_text(ctx.doc)),
		gate_text(gate) if gate else _("AI model not used: the check could not run."),
	]


def finalize(ctx):
	"""Keep the brief on the run and post it in the Issue chat (when the record chat is on)."""
	lines = brief_lines(ctx)
	ctx.summary = "\n".join(lines)
	if not ctx.agent.raven_bot:
		return
	html = f"<p><strong>{escape_html(lines[0])}</strong></p><ul>" + "".join(
		f"<li>{escape_html(line)}</li>" for line in lines[1:]
	) + "</ul>"
	frappe.db.savepoint("issue_assistant_brief")
	try:
		from phamos.api.issue_chat import post_bot_message

		post_bot_message(ctx.doc, ctx.agent.raven_bot, html)
	except Exception:
		# the brief stays on the run; a broken chat must not fail the assistant's work
		frappe.db.rollback(save_point="issue_assistant_brief")
		frappe.log_error(title=f"Issue Assistant: could not post the brief on {ctx.doc.name}")
		ctx.flags.append({"code": "brief_not_posted", "severity": "warn",
			"message": _("The brief could not be posted in the Issue chat.")})
