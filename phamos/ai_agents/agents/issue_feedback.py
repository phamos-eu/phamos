# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Issue Assistant, learning from corrections (#2225), on the generic loop (phamos/ai_agents/feedback.py).

A correction is a person changing what the assistant's latest run on an Issue did:
- a field the run set (customer, contact, Implementation, project from Identify; issue type, priority
  from Classify) now holds another value,
- the person the run assigned is no longer assigned, or a person assigns someone other than the one
  the run suggested.
Changes made through the chat (#2116) count, since they are saved as the asker. A change by any AI
agent's user never counts.

Suggestions, never applied before a trainer accepts them:
- an Identify mistake becomes a **mapping rule**: AI Skill phase Identify, handler `sender_mapping`,
  params {"match": sender e-mail, "values": {field: value}}; Identify applies accepted ones first,
- a Classify or person mistake becomes a **prompt rule** for the Issue's Customer: AI Skill phase
  Classify, party Customer; Classify adds accepted ones to the model's prompt. Its wording is a
  template; the model redrafts it in the background when the Customer allows the AI model.

A run nobody corrected becomes Accepted after "Accept after (days)" or when its Issue is closed.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr

from phamos.ai_agents import feedback

IDENTIFY_FIELDS = ("customer", "contact", "custom_implementation", "project")
CLASSIFY_FIELDS = ("issue_type", "priority")
PERSON = "person"
GROUPS = {**{f: "identify" for f in IDENTIFY_FIELDS}, **{f: "classify" for f in CLASSIFY_FIELDS}, PERSON: "person"}
MAPPING_HANDLER = "sender_mapping"
DONE_STATUSES = ("Closed", "Resolved")
DEFAULT_ACCEPT_AFTER_DAYS = 7
DEFAULT_STATS_WINDOW_DAYS = 90


def agent_name():
	from phamos.setup.issue_assistant import ASSISTANT_NAME

	return ASSISTANT_NAME


def settings_days(field, default):
	from phamos.ai_agents.agents.issue import SETTINGS

	return cint(frappe.db.get_single_value(SETTINGS, field)) or default


# --- what the run did ----------------------------------------------------------------------------


def run_values(run):
	"""{field: the value the run set} for the fields in its fields_set."""
	analysis = frappe.parse_json(run.analysis or "{}") or {}
	identify = analysis.get("identify") or {}
	answer = (analysis.get("classify") or {}).get("answer") or {}
	values = {}
	for field in (f.strip() for f in cstr(run.fields_set).split(",") if f.strip()):
		if field in IDENTIFY_FIELDS:
			key = "implementation" if field == "custom_implementation" else field
			values[field] = (identify.get(key) or {}).get("value")
		elif field in CLASSIFY_FIELDS:
			values[field] = (answer.get(field) or {}).get("value") if isinstance(answer.get(field), dict) else None
	return values


def run_person(run):
	"""The person the run picked: {"user", "assigned"} or None."""
	analysis = frappe.parse_json(run.analysis or "{}") or {}
	person = (analysis.get("classify") or {}).get("person")
	return person if isinstance(person, dict) and person.get("user") else None


# an assignment that is still there: Closed means the person finished it, only Cancelled means removed
# (AI review on !1392)
ASSIGNED = ("Open", "Closed")


def human_assignees(issue_name):
	"""Users assigned to the Issue by a person (not by an AI agent), not removed."""
	ai = feedback.ai_users()
	rows = frappe.get_all("ToDo", filters={"reference_type": "Issue", "reference_name": issue_name,
		"status": ("in", ASSIGNED)}, fields=["allocated_to", "assigned_by"])
	return sorted({r.allocated_to for r in rows if r.allocated_to not in ai and r.assigned_by not in ai})


def corrections_for(doc, run):
	"""[{field, ai_value, human_value, group}] where the Issue no longer holds what the run did."""
	found = []
	for field, ai_value in run_values(run).items():
		value = doc.get(field)
		if cstr(ai_value) != cstr(value):
			found.append({"field": field, "ai_value": ai_value, "human_value": value or None, "group": GROUPS[field]})
	person = run_person(run)
	if person:
		user = person["user"]
		open_for_user = frappe.db.exists("ToDo", {"reference_type": "Issue", "reference_name": doc.name,
			"allocated_to": user, "status": ("in", ASSIGNED)})
		others = [u for u in human_assignees(doc.name) if u != user]
		if (person.get("assigned") and not open_for_user) or (not person.get("assigned") and others and not open_for_user):
			found.append({"field": PERSON, "ai_value": user, "human_value": ", ".join(others) or None, "group": "person"})
	return found


# --- collecting (hooks) --------------------------------------------------------------------------


def collect(doc, user=None):
	"""After a person changed an Issue or its assignment: corrections on the latest run, suggestions for new
	ones. Returns the corrections, or None when there is nothing to compare."""
	user = user or frappe.session.user
	if feedback.is_ai_user(user):
		return None
	run = feedback.latest_run(agent_name(), "Issue", doc.name)
	if not run:
		return None
	found = corrections_for(doc, run)
	for correction in feedback.record(run, found, user, done=doc.get("status") in DONE_STATUSES, keep_accepted=True,
			corrector_of_new=True):
		suggest(doc, run, correction)
	return found


def on_issue_update(doc, method=None):
	"""Issue on_update: never blocks the save."""
	_safely(doc.name, lambda: collect(doc))


def on_todo_update(doc, method=None):
	"""ToDo on_update: an assignment on an Issue changed. Never blocks the save."""
	if doc.reference_type != "Issue" or not doc.reference_name:
		return
	_safely(doc.reference_name, lambda: collect(frappe.get_doc("Issue", doc.reference_name)))


def _safely(issue_name, work):
	if frappe.flags.in_install or frappe.flags.in_migrate or feedback.is_ai_user(frappe.session.user):
		return
	try:
		work()
	except Exception:
		frappe.log_error(title=f"Issue Assistant: learning from {issue_name} failed")


def mark_accepted_daily():
	"""Daily: runs nobody corrected for "Accept after (days)", or whose Issue is closed, become Accepted."""
	def closed(doctype, names):
		return frappe.get_all(doctype, filters={"name": ("in", names), "status": ("in", DONE_STATUSES)}, pluck="name")

	return feedback.mark_accepted(agent_name(), settings_days("accept_after_days", DEFAULT_ACCEPT_AFTER_DAYS), closed)


def rates():
	"""Correction rates per step (identify, classify, person) and per field over the statistics window."""
	return feedback.rates(agent_name(), settings_days("stats_window_days", DEFAULT_STATS_WINDOW_DAYS), GROUPS)


# --- suggestions ---------------------------------------------------------------------------------


def suggest(doc, run, correction):
	if correction["group"] == "identify":
		return suggest_mapping(doc, run, correction)
	return suggest_prompt_rule(doc, run, correction)


def _label(field):
	if field == PERSON:
		return _("person")
	return _(frappe.get_meta("Issue").get_label(field))


def suggest_mapping(doc, run, correction):
	"""A sender → value rule for Identify. Not when the value was only cleared, or the sender is unknown."""
	from phamos.ai_agents.agents.issue_identify import sender_email

	from phamos.marketing.crm import employee_for_email

	email = cstr(sender_email(doc)).strip().lower()
	field, value = correction["field"], correction["human_value"]
	if not email or not value or employee_for_email(email):
		# a colleague files Issues for many customers: a rule on their address would map all of them to one
		# (AI review on !1392)
		return None
	# the value is part of the key: another value is another suggestion, and a dismissed wrong one doesn't
	# block a right one (AI review on !1392)
	key = f"Issue::sender::{email}::{field}::{value}"
	who = frappe.utils.get_fullname(correction.get("user") or frappe.session.user)

	def make():
		return {
			"skill_name": _("E-mails from {0}: {1} {2}").format(email, _label(field), value)[:140],
			"phase": "Identify",
			"order": 5,
			"handler": MAPPING_HANDLER,
			"on_fail": "Continue",
			"params": frappe.as_json({"match": email, "values": {field: value}}),
			"description": _("Suggested after {0} changed {1} from {2} to {3} on {4}.").format(
				who, _label(field), correction["ai_value"] or "–", value, doc.name),
		}

	return feedback.suggestion(key, run, make)


def suggest_prompt_rule(doc, run, correction):
	"""A rule for the model, for this Customer's Issues. Not without a Customer."""
	from phamos.ai_agents.agents.issue import customer_of

	customer = customer_of(doc)
	if not customer:
		return None
	field = correction["field"]
	key = f"Issue::rule::{customer}::{field}::{correction['ai_value'] or ''}->{correction['human_value'] or ''}"
	customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
	who = frappe.utils.get_fullname(correction.get("user") or frappe.session.user)
	ai_value, human_value = _display(field, correction["ai_value"]), _display(field, correction["human_value"])

	def make():
		return {
			"skill_name": _("{0}: {1}").format(customer_name, _label(field))[:140],
			"phase": "Classify",
			"order": 50,
			"party_doctype": "Customer",
			"party": customer,
			"on_fail": "Continue",
			"description": _("Suggested after {0} corrected the {1} on {2}.").format(who, _label(field), doc.name),
			"prompt_rules": [{
				"enabled": 1,
				"order": 1,
				"case_description": _("Issues from {0} like \"{1}\"").format(customer_name, cstr(doc.subject)[:120]),
				"action": template_action(field, ai_value, human_value),
				"reason": _("{0} changed \"{1}\" to \"{2}\" on {3} ({4}).").format(
					who, ai_value or "–", human_value or "–", doc.name, run.name),
			}],
		}

	name = feedback.suggestion(key, run, make)
	if name and frappe.db.get_value("AI Skill", name, "occurrences") == 1:
		frappe.enqueue(draft_wording, queue="long", timeout=120, skill=name, issue=doc.name, enqueue_after_commit=True)
	return name


def _display(field, value):
	if field == PERSON and value:
		return ", ".join(frappe.utils.get_fullname(u.strip()) for u in cstr(value).split(",") if u.strip())
	return cstr(value) or None


def template_action(field, ai_value, human_value):
	if field == PERSON:
		if human_value:
			return _("Suggest {0} as the person for such Issues, not {1}.").format(human_value, ai_value)
		return _("Don't suggest {0} as the person for such Issues.").format(ai_value)
	if human_value:
		return _("Such Issues have the {0} \"{1}\", not \"{2}\".").format(_label(field), human_value, ai_value)
	return _("Leave the {0} empty for such Issues instead of \"{1}\".").format(_label(field), ai_value)


DRAFT_SYSTEM = (
	"You write one short rule for an AI that classifies support Issues of one customer. You get an Issue and "
	"how a person corrected the AI. Write when the rule applies (case_description, a few words, general enough "
	"for similar Issues of this customer) and what to do (action, one sentence). Use only the given data. "
	"Answer with one JSON object {\"case_description\": \"...\", \"action\": \"...\"}."
)


def draft_wording(skill, issue):
	"""Background: let the model word a new prompt rule better, only when the gate allows the model for this
	Issue. The template text stays when it doesn't, or when anything fails."""
	from phamos.ai_agents import llm
	from phamos.ai_agents.agents.issue import model_allowed

	skill_doc = frappe.get_doc("AI Skill", skill)
	if skill_doc.origin != feedback.SUGGESTED or not skill_doc.prompt_rules:
		return
	doc = frappe.get_doc("Issue", issue)
	if not model_allowed(doc).get("allowed"):
		return
	rule = skill_doc.prompt_rules[0]
	data = {"issue": {"subject": doc.subject, "description": frappe.utils.strip_html_tags(cstr(doc.description))[:2000]},
		"correction": rule.reason, "current_rule": {"case_description": rule.case_description, "action": rule.action}}
	try:
		answer, _model = llm.chat_json(frappe.as_json(data, indent=1), system=DRAFT_SYSTEM)
	except Exception:
		frappe.log_error(title=f"Issue Assistant: drafting rule {skill} failed")
		return
	answer = answer if isinstance(answer, dict) else {}
	case, action = cstr(answer.get("case_description")).strip(), cstr(answer.get("action")).strip()
	if not (case and action):
		return
	# the call takes a while: write only when nobody accepted, enabled or edited the rule meanwhile, so text
	# drawn from the customer's Issue never lands in a rule a person already approved (AI review on !1392)
	now = frappe.db.get_value("AI Skill", skill, ["origin", "enabled"], as_dict=True, for_update=True)
	current = frappe.db.get_value("AI Prompt Rule", rule.name, ["case_description", "action"], as_dict=True)
	if (not now or now.origin != feedback.SUGGESTED or now.enabled or not current
			or (current.case_description, current.action) != (rule.case_description, rule.action)):
		return
	frappe.db.set_value("AI Prompt Rule", rule.name, {"case_description": case[:500], "action": action[:1000]})
	frappe.db.commit()  # nosemgrep: background job
