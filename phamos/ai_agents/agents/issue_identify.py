# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Issue Assistant, Identify (#2112): who sent the Issue and what it belongs to, in code, no model.

From the sender's e-mail: the Employee (named only, never makes the Issue internal), the Contact and
Customer (marketing.crm.find_party), then the Implementation and the open Project. Writes customer,
contact, custom_implementation and project only when empty and the match is strong; a value a human
set is never overwritten. Phriend's default project counts as empty while no one changed it. Review
cases write nothing and become a question in the brief. After setting the Customer the gate is
checked again, so Classify (#2113) sees the new answer.
"""

import frappe
from frappe import _

from phamos.ai_agents.context import PASSED, SkillResult

STRONG, REVIEW, NONE = "strong", "review", "none"
CLOSED_IMPLEMENTATION = ("Cancelled", "Completed")


def run_identify(ctx, skill):
	"""Skill "Identify sender and links" (phase Identify)."""
	from phamos.ai_agents.agents.issue import gate_for

	doc = ctx.doc
	found = identify(doc)
	changes = {}
	if found["customer"]["confidence"] == STRONG and not doc.get("customer"):
		changes["customer"] = found["customer"]["value"]
	if found["contact"]["confidence"] == STRONG and not doc.get("contact"):
		changes["contact"] = found["contact"]["value"]
	if found["implementation"]["confidence"] == STRONG and not doc.get("custom_implementation"):
		changes["custom_implementation"] = found["implementation"]["value"]
	if found["project"]["confidence"] == STRONG and project_is_empty(doc):
		if found["project"]["value"] != doc.get("project"):
			changes["project"] = found["project"]["value"]
	from phamos.ai_agents.agents.issue_classify import save_changes

	# reloaded inside; a field a person filled meanwhile is left alone
	changes = {f: changes[f] for f in save_changes(doc, changes,
		lambda d, field: project_is_empty(d) if field == "project" else not d.get(field))}
	found["fields_set"] = list(changes)
	ctx.analysis["identify"] = found
	if "customer" in changes or "custom_implementation" in changes:
		ctx.analysis["gate"] = gate_for(ctx)
	return SkillResult(status=PASSED, message=_("Identified: {0}").format(", ".join(changes) or _("nothing set")),
		fields_set=list(changes), output={k: v for k, v in found.items() if k != "fields_set"})


def sender_email(doc):
	"""The reporter's address: Phriend's reporter (a User) first, else raised_by."""
	user = doc.get("phriend_reported_by")
	if user:
		email = frappe.db.get_value("User", user, "email")
		if email:
			return email
	return (doc.get("raised_by") or "").strip() or None


def _result(value=None, confidence=NONE, candidates=None, via=None):
	return {"value": value, "confidence": confidence, "candidates": candidates or [], "via": via}


def identify(doc):
	"""{"email", "employee", "customer", "contact", "implementation", "project"}: each a result dict
	with value, confidence (strong / review / none), candidates and how it was found."""
	from phamos.marketing.crm import employee_for_email, find_party

	email = sender_email(doc)
	out = {"email": email, "employee": _result()}
	learned = learned_values(email)  # accepted mapping rules (#2225) come before everything found by data
	party = find_party(email) if email else frappe._dict(customers=[], customer=None, contact=None, confidence=NONE)
	employee = employee_for_email(email) if email else None
	if employee:
		out["employee"] = _result(employee, STRONG, via="email")

	# Customer and Contact: the Issue's own values first, then the sender's Contact
	if doc.get("customer") and doc.customer in (party.customers or []) and len(party.customers) > 1 \
			and not changed_by_hand(doc, "customer"):
		# ERPNext's Issue.set_lead_contact took the Contact's first Customer: keep it, but ask
		out["customer"] = _result(doc.customer, REVIEW, candidates=list(party.customers), via="erpnext")
	elif doc.get("customer"):
		out["customer"] = _result(doc.customer, STRONG, via="issue")
	elif learned.get("customer"):
		out["customer"] = _result(learned["customer"], STRONG, via="rule")
	elif party.customer and party.confidence == STRONG:
		out["customer"] = _result(party.customer, STRONG, via="contact")
	elif len(party.customers or []) > 1:
		out["customer"] = _result(confidence=REVIEW, candidates=list(party.customers), via="contact")
	else:
		out["customer"] = _result()
	# the sender's Contact is strong when it is the found Customer's: found through it, or the Issue's own Customer
	# is one of its links (AI review on !1345)
	contact_strong = bool(party.contact) and out["customer"]["confidence"] == STRONG and (
		out["customer"]["via"] == "contact" or out["customer"]["value"] in (party.customers or []))
	out["contact"] = _result(party.contact, STRONG if contact_strong else NONE, via="email")
	if learned.get("contact") and _contact_fits(learned["contact"], out["customer"]["value"]):
		out["contact"] = _result(learned["contact"], STRONG, via="rule")

	out["implementation"] = find_implementation(doc, out["customer"], email, learned)
	# an Implementation found by a stakeholder row tells the Customer too (Implementation.customer is required)
	if out["customer"]["confidence"] == NONE and out["implementation"]["confidence"] == STRONG:
		customer = frappe.db.get_value("Implementation", out["implementation"]["value"], "customer")
		if customer:
			out["customer"] = _result(customer, STRONG, via="implementation")
	out["project"] = find_project(doc, out["implementation"], learned)
	return out


def find_implementation(doc, customer, email, learned=None):
	if doc.get("custom_implementation"):
		return _result(doc.custom_implementation, STRONG, via="issue")
	if (learned or {}).get("custom_implementation"):
		return _result(learned["custom_implementation"], STRONG, via="rule")
	if customer["confidence"] == STRONG:
		names = frappe.get_all("Implementation", filters={"customer": customer["value"],
			"status": ("not in", CLOSED_IMPLEMENTATION)}, pluck="name", order_by="name asc")
		if len(names) == 1:
			return _result(names[0], STRONG, via="customer")
		if names:
			return _result(confidence=REVIEW, candidates=names, via="customer")
	if email:
		names = frappe.get_all("Implementation Stakeholder", filters={"parenttype": "Implementation",
			"email": email}, pluck="parent", distinct=True)
		rows = frappe.get_all("Implementation", filters={"name": ("in", names or [""]),
			"status": ("not in", CLOSED_IMPLEMENTATION)}, fields=["name", "customer"], order_by="name asc")
		if customer["value"]:
			# a known Customer (also ERPNext's pick) only takes its own Implementations; another Customer's
			# becomes a question, never a write (AI review on !1345)
			own = [r.name for r in rows if r.customer == customer["value"]]
			if len(own) == 1 and customer["confidence"] == STRONG:
				return _result(own[0], STRONG, via="stakeholder")
			if rows:
				return _result(confidence=REVIEW, candidates=[r.name for r in rows], via="stakeholder")
		elif len(rows) == 1:
			return _result(rows[0].name, STRONG, via="stakeholder")
		elif rows:
			return _result(confidence=REVIEW, candidates=[r.name for r in rows], via="stakeholder")
	return _result()


def find_project(doc, implementation, learned=None):
	if not project_is_empty(doc):
		return _result(doc.project, STRONG, via="issue")
	if (learned or {}).get("project") and _project_fits(learned["project"], implementation):
		return _result(learned["project"], STRONG, via="rule")
	if implementation["confidence"] != STRONG:
		return _result()
	names = frappe.get_all("Project", filters={"custom_implementation": implementation["value"], "status": "Open"},
		pluck="name", order_by="name asc")
	if len(names) == 1:
		return _result(names[0], STRONG, via="implementation")
	if names:
		return _result(confidence=REVIEW, candidates=names, via="implementation")
	return _result()


def learned_values(email):
	"""{field: value} from the assistant's accepted mapping rules (#2225) for this sender: an exact e-mail
	rule wins over a domain rule. Values whose record no longer exists are left out."""
	from phamos.ai_agents.agents.issue_feedback import MAPPING_HANDLER, agent_name

	email = (email or "").strip().lower()
	if not email:
		return {}
	domain = email.split("@")[-1]
	rows = frappe.get_all("AI Skill", filters={"agent": agent_name(), "handler": MAPPING_HANDLER, "enabled": 1,
		"dismissed": 0}, fields=["params"], order_by="`order` asc, creation asc")
	by_domain, by_email = {}, {}
	for row in rows:
		params = frappe.parse_json(row.params or "{}") or {}
		match = (params.get("match") or "").strip().lower()
		target = by_email if match == email else by_domain if match == domain else None
		if target is None:
			continue
		for field, value in (params.get("values") or {}).items():
			if field in LINK_DOCTYPES and value and frappe.db.exists(LINK_DOCTYPES[field], value):
				target.setdefault(field, value)
	return {**by_domain, **by_email}


def _contact_fits(contact, customer):
	"""A learned Contact only with its own Customer (or when no Customer is known)."""
	return not customer or bool(frappe.db.exists("Dynamic Link", {"parenttype": "Contact", "parent": contact,
		"link_doctype": "Customer", "link_name": customer}))


def _project_fits(project, implementation):
	"""A learned Project only within the Implementation found (or when none is known)."""
	if not implementation.get("value"):
		return True
	return frappe.db.get_value("Project", project, "custom_implementation") in (None, "", implementation["value"])


LINK_DOCTYPES = {"customer": "Customer", "contact": "Contact", "custom_implementation": "Implementation",
	"project": "Project"}


def run_sender_mapping(ctx, skill):
	"""Step of an accepted mapping rule (#2225): says whether it matches this sender. Identify applies it."""
	from phamos.ai_agents.context import SKIPPED

	params = frappe.parse_json(skill.params or "{}") or {}
	match = (params.get("match") or "").strip().lower()
	email = (sender_email(ctx.doc) or "").strip().lower()
	if match and email and match in (email, email.split("@")[-1]):
		return SkillResult(status=PASSED, message=_("Learned rule for {0}").format(match))
	return SkillResult(status=SKIPPED, message=_("Not this sender"))


def changed_by_hand(doc, field):
	"""Whether someone other than the assistant changed the field after the Issue was created.

	Reads the Issue's versions (Issue has track_changes): a version whose "changed" list names the field,
	saved by anyone but the assistant's user. The assistant's own writes don't count, so they never lock a
	value it set (AI review on !1345). The LIKE only narrows the rows; the JSON decides.
	"""
	from phamos.setup.issue_assistant import ASSISTANT_NAME

	assistant = frappe.db.get_value("AI Agent", ASSISTANT_NAME, "user")
	rows = frappe.get_all("Version", filters={"ref_doctype": "Issue", "docname": doc.name,
		"data": ("like", f'%"{field}"%')}, fields=["owner", "data"])
	for row in rows:
		if row.owner == assistant:
			continue
		try:
			changed = (frappe.parse_json(row.data) or {}).get("changed") or []
		except Exception:
			return True  # unreadable: assume a person changed it, so nothing is overwritten
		if any(isinstance(c, (list, tuple)) and c and c[0] == field for c in changed):
			return True
	return False


def project_is_empty(doc):
	"""Empty, or Phriend's default project that no one changed since (decision 3)."""
	if not doc.get("project"):
		return True
	if not doc.get("phriend_type"):
		return False
	default = frappe.db.get_single_value("Phriend Settings", "default_project")
	if not default or doc.project != default:
		return False
	return not changed_by_hand(doc, "project")


# --- brief -----------------------------------------------------------------------------------


def brief_lines(ctx):
	found = ctx.analysis.get("identify")
	if not found:
		return []
	lines = []
	if found["employee"]["value"]:
		name = frappe.db.get_value("Employee", found["employee"]["value"], "employee_name")
		lines.append(_("Likely sender: employee {0} (by e-mail address only)").format(name or found["employee"]["value"]))
	set_fields = found.get("fields_set") or []
	for key, field, label in (("customer", "customer", _("Customer")), ("contact", "contact", _("Contact")),
			("implementation", "custom_implementation", _("Implementation")), ("project", "project", _("Project"))):
		item = found[key]
		if field in set_fields:
			lines.append(_("{0} set: {1}").format(label, item["value"]))
		elif item["confidence"] == REVIEW:
			names = [_label(key, c) for c in item["candidates"]]
			line = _("Which {0} is it: {1}?").format(label, " / ".join(names))
			if item["via"] == "erpnext":
				line += " " + _("(ERPNext picked {0})").format(item["value"])
			lines.append(line)
	return lines


def _label(key, name):
	if key == "project":
		title = frappe.db.get_value("Project", name, "project_name")
		return f"{name} ({title})" if title and title != name else name
	return name
