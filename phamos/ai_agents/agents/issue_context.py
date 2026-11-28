# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Issue Assistant, what the chat answer may know about an Issue beyond its own fields (#2238, #2230).

Everything here is posted into a Raven chat that all its members read, so a record is used only when
**every** human member of the Issue's chat may read it (decision 1 of #2230). It also goes to the AI model,
so (decision 5):
- only records of this Issue's customer: related Issues of another customer never;
- timesheets with date, person, hours and activity, never rates, amounts or costs;
- nothing from HR, salary or leave records (none of those doctypes is read here);
- e-mails of this Issue only.
Lists are capped so the prompt stays small.
"""

import frappe
from frappe.utils import cstr, strip_html_tags

MAX_RELATED = 20
MAX_COMMENTS = 20
MAX_EMAILS = 10
MAX_CHANGES = 20
MAX_TIME_ROWS = 50
MAX_GITLAB = 20
MAX_TEXT = 600


def readers(issue_name, asker=None):
	"""The people who read the Issue chat: its human members (Raven users of type User, not AI agents), plus the asker."""
	from phamos.api.issue_chat import find_channel

	users = set()
	channel = find_channel("Issue", issue_name)
	if channel:
		members = frappe.get_all("Raven Channel Member", filters={"channel_id": channel.name}, pluck="user_id")
		users = set(frappe.get_all("Raven User", filters={"name": ("in", members or [""]), "type": "User",
			"enabled": 1, "user": ("is", "set")}, pluck="user"))
	# AI agents' own users are members too, but no reader: their rights must not narrow what people see
	users -= set(frappe.get_all("AI Agent", filters={"user": ("is", "set")}, pluck="user"))
	if asker:
		users.add(asker)
	return sorted(users)


def readable(doctype, name, people):
	"""Whether every one of `people` may read the record. Nobody known: no (AI review on !1406)."""
	if not people:
		return False
	doc = frappe.get_doc(doctype, name)  # loaded once, not once per person
	return all(frappe.has_permission(doctype, "read", doc=doc, user=user) for user in people)


def _of_customer(doctype, name, customer):
	"""Whether a linked record belongs to this Issue's customer, so another customer's data never goes to the
	model (AI review on !1406). Without a customer only records without one."""
	if doctype == "Contact":
		if not customer:
			return not frappe.db.exists("Dynamic Link", {"parenttype": "Contact", "parent": name,
				"link_doctype": "Customer"})
		return bool(frappe.db.exists("Dynamic Link", {"parenttype": "Contact", "parent": name,
			"link_doctype": "Customer", "link_name": customer}))
	if doctype in ("Project", "Implementation"):
		return (frappe.db.get_value(doctype, name, "customer") or None) == (customer or None)
	return doctype != "Customer" or name == customer


def _short(text, limit=MAX_TEXT):
	text = " ".join(strip_html_tags(cstr(text)).split())
	return text if len(text) <= limit else text[: limit - 1] + "…"


def build(issue, people):
	"""The context for the chat answer: {related_issues, linked_records, activity, time, gitlab}."""
	from phamos.ai_agents.agents.issue import customer_of

	customer = customer_of(issue)
	return {
		"related_issues": related_issues(issue, customer, people),
		"linked_records": linked_records(issue, customer, people),
		"activity": activity(issue, people),
		"time": time_booked(issue, people),
		"gitlab": gitlab_issues(issue, people),
	}


def related_issues(issue, customer, people):
	"""Other Issues of the same project, customer or Implementation, newest first; only this customer's
	(without a customer: only Issues without one)."""
	links = {f: issue.get(f) for f in ("project", "custom_implementation") if issue.get(f)}
	if customer:
		links["customer"] = customer
	if not links:
		return []
	or_filters = [["Issue", f, "=", v] for f, v in links.items()]
	rows = frappe.get_all("Issue", filters={"name": ("!=", issue.name), "customer": customer or ("is", "not set")},
		or_filters=or_filters, fields=["name", "subject", "status", "priority", "opening_date", "_assign"],
		order_by="creation desc", limit_page_length=MAX_RELATED * 3)
	from phamos.ai_agents.agents.issue import model_allowed

	out = []
	for row in rows:
		if not readable("Issue", row.name, people):
			continue
		# the gate of each related Issue too: e.g. an outside sender's Issue on an internal project stays out
		# of the model even when this one is internal (AI review on !1406)
		if not model_allowed(frappe.get_doc("Issue", row.name)).get("allowed"):
			continue
		assignees = frappe.parse_json(row._assign or "[]") or []
		out.append({"name": row.name, "subject": _short(row.subject, 140), "status": row.status, "priority": row.priority,
			"opened": str(row.opening_date or ""), "assigned": [frappe.utils.get_fullname(u) for u in assignees]})
		if len(out) >= MAX_RELATED:
			break
	return out


def linked_records(issue, customer, people):
	"""Key fields of the Issue's Customer, Contact, Implementation and Project (only this customer's), and its
	open ToDos."""
	out = {}
	specs = (
		("customer", "Customer", ["customer_name", "customer_group"]),
		("contact", "Contact", ["full_name", "email_id"]),
		("custom_implementation", "Implementation", ["status", "account_manager"]),
		("project", "Project", ["project_name", "status"]),
	)
	for field, doctype, fields in specs:
		name = issue.get(field)
		if not name or not frappe.db.exists(doctype, name) or not _of_customer(doctype, name, customer) \
				or not readable(doctype, name, people):
			continue
		row = frappe.db.get_value(doctype, name, fields, as_dict=True) or {}
		if row.get("account_manager"):
			row["account_manager"] = frappe.utils.get_fullname(row["account_manager"])
		out[doctype.lower()] = {"name": name, **row}
	todos = frappe.get_all("ToDo", filters={"reference_type": "Issue", "reference_name": issue.name, "status": "Open"},
		fields=["name", "allocated_to", "description", "date"])
	# a ToDo of a readable Issue is part of the Issue (its assignees show on it anyway); Frappe's own ToDo check
	# lets only assignee and assigner read it (AI review on !1406)
	issue_readable = readable("Issue", issue.name, people)
	out["open_todos"] = [{"for": frappe.utils.get_fullname(t.allocated_to), "what": _short(t.description, 200),
		"due": str(t.date or "")} for t in todos] if issue_readable else []
	return out


def activity(issue, people):
	"""The Issue's comments, its e-mails and its change history, newest first. Readable by everyone who may read
	the Issue (checked by the caller), so no per-row check beyond that."""
	if not readable("Issue", issue.name, people):
		return {}
	comments = frappe.get_all("Comment", filters={"reference_doctype": "Issue", "reference_name": issue.name,
		"comment_type": "Comment"}, fields=["comment_by", "owner", "content", "creation"], order_by="creation desc",
		limit_page_length=MAX_COMMENTS)
	emails = frappe.get_all("Communication", filters={"reference_doctype": "Issue", "reference_name": issue.name,
		"communication_medium": "Email"}, fields=["sent_or_received", "sender", "subject", "content", "creation"],
		order_by="creation desc", limit_page_length=MAX_EMAILS)
	versions = frappe.get_all("Version", filters={"ref_doctype": "Issue", "docname": issue.name},
		fields=["owner", "data", "creation"], order_by="creation desc", limit_page_length=MAX_CHANGES)
	visible = visible_fields(people)
	changes = []
	for version in versions:
		data = frappe.parse_json(version.data or "{}") or {}
		for change in data.get("changed") or []:
			if isinstance(change, (list, tuple)) and len(change) == 3 and change[0] in visible:
				changes.append({"field": change[0], "from": _short(change[1], 80), "to": _short(change[2], 80),
					"by": frappe.utils.get_fullname(version.owner), "when": str(version.creation)})
	return {
		"comments": [{"by": c.comment_by or frappe.utils.get_fullname(c.owner), "text": _short(c.content),
			"when": str(c.creation)} for c in comments],
		"emails": [{"direction": e.sent_or_received, "from": e.sender, "subject": _short(e.subject, 140),
			"text": _short(e.content), "when": str(e.creation)} for e in emails],
		"changes": changes[:MAX_CHANGES],
	}


def visible_fields(people):
	"""Issue fields whose changes every reader may see: shown on the timeline (not hidden, or marked "show on
	timeline") and at a permission level each reader may read (AI review on !1406)."""
	meta = frappe.get_meta("Issue")
	levels = None
	for user in people:
		user_levels = set(meta.get_permlevel_access("read", user=user)) | {0}
		levels = user_levels if levels is None else levels & user_levels
	levels = levels or {0}
	return {df.fieldname for df in meta.fields
		if (not df.hidden or df.show_on_timeline) and (df.permlevel or 0) in levels}


def time_booked(issue, people):
	"""Timesheet rows of the Issue's Tasks: date, person, hours, activity. Never rates, amounts or costs."""
	tasks = frappe.get_all("Task", filters={"issue": issue.name}, pluck="name")
	if not tasks:
		return []
	detail, sheet = frappe.qb.DocType("Timesheet Detail"), frappe.qb.DocType("Timesheet")
	rows = (
		frappe.qb.from_(detail).join(sheet).on(detail.parent == sheet.name)
		.select(sheet.name.as_("timesheet"), sheet.employee_name, detail.from_time, detail.hours, detail.activity_type,
			detail.task)
		.where(detail.task.isin(tasks)).where(sheet.docstatus < 2)
		.orderby(detail.from_time, order=frappe.qb.desc).limit(MAX_TIME_ROWS)
	).run(as_dict=True)
	allowed = {}
	out = []
	for row in rows:
		if row.timesheet not in allowed:
			allowed[row.timesheet] = readable("Timesheet", row.timesheet, people)
		if allowed[row.timesheet]:
			out.append({"date": str(row.from_time or "")[:10], "person": row.employee_name, "hours": row.hours,
				"activity": row.activity_type, "task": row.task})
	return out


def gitlab_issues(issue, people):
	if not frappe.db.exists("DocType", "GitLab Issue"):
		return []
	rows = frappe.get_all("GitLab Issue", filters={"issue": issue.name}, fields=["name", "title", "state", "issue_url"],
		order_by="creation desc", limit_page_length=MAX_GITLAB)
	return [{"title": _short(r.title, 200), "state": r.state, "url": r.issue_url} for r in rows
		if readable("GitLab Issue", r.name, people)]
