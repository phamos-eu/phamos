# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Issue Assistant, open questions as Raven polls (#2232, decision 6 of #2228).

Where the brief asks something, the assistant posts a single-choice, non-anonymous Raven poll in the
Issue chat: the candidates plus "None of these".
- Customer, Implementation, project: Identify's review candidates (#2112).
- Person: the person Classify suggested but did not assign (#2113), plus other candidates.

The poll remembers its Issue, field and the value behind each option on the run's analysis
(`analysis.polls[<poll>]`), never from the option's text. The first vote by someone who may write the
Issue is applied in that person's session: the field is set, or the person assigned. The assistant then
closes the poll and confirms in the chat. Votes by others change nothing (noted once per poll). A choice
that differs from what the run set is a correction for #2225, since it is saved as the voter.
Raven itself is unchanged: polls are standard Raven, the reaction is a doc_event on Raven Poll Vote.
"""

import frappe
from frappe import _
from frappe.utils import cstr, escape_html

NONE = "__none__"
MAX_PERSON_OPTIONS = 4
# Identify's keys → Issue fields and the labels used in the brief
IDENTIFY_FIELDS = (("customer", "customer"), ("implementation", "custom_implementation"), ("project", "project"))
PERSON = "person"


# --- the questions -------------------------------------------------------------------------------


def questions(ctx):
	"""[{field, question, options: [(label, value)]}] for the brief's open questions."""
	from phamos.ai_agents.agents.issue_identify import REVIEW, _label

	out = []
	found = ctx.analysis.get("identify") or {}
	for key, field in IDENTIFY_FIELDS:
		item = found.get(key) or {}
		if item.get("confidence") == REVIEW and item.get("candidates") and field not in (found.get("fields_set") or []):
			label = _(frappe.get_meta("Issue").get_label(field))
			out.append({"field": field, "question": _("Which {0} is it?").format(label),
				"options": [(_label(key, c), c) for c in item["candidates"]]})
	classify = ctx.analysis.get("classify") or {}
	person = classify.get("person")
	if person and not person.get("assigned"):
		users = [person["user"]] + [u for u in classify.get("candidates") or [] if u != person["user"]]
		users = [u for u in users if u != ctx.agent.user][:MAX_PERSON_OPTIONS]
		out.append({"field": PERSON, "question": _("Whom should I assign?"),
			"options": [(frappe.utils.get_fullname(u), u) for u in users]})
	return out


# --- posting -------------------------------------------------------------------------------------


def post_polls(ctx):
	"""After the brief: one poll per open question in the Issue chat. Returns the poll names."""
	from phamos.api.issue_chat import find_channel

	channel = find_channel("Issue", ctx.doc.name)
	if not channel or not ctx.agent.raven_bot:
		return []
	bot_user = frappe.db.get_value("Raven Bot", ctx.agent.raven_bot, "raven_user")
	polls = ctx.analysis.setdefault("polls", {})
	for item in questions(ctx):
		poll = frappe.get_doc({"doctype": "Raven Poll", "question": item["question"], "is_multi_choice": 0,
			"is_anonymous": 0})
		for label, _value in item["options"]:
			poll.append("options", {"option": cstr(label)[:140]})
		poll.append("options", {"option": _("None of these")})
		poll.insert(ignore_permissions=True)
		values = {row.name: value for row, (_label, value) in zip(poll.options, item["options"])}
		values[poll.options[-1].name] = NONE
		content = item["question"] + "\n" + "".join(f"{i + 1}. {row.option}\n" for i, row in enumerate(poll.options))
		message = frappe.get_doc({"doctype": "Raven Message", "channel_id": channel.name, "text": "", "content": content,
			"message_type": "Poll", "poll_id": poll.name, "is_bot_message": 1, "bot": bot_user})
		message.insert(ignore_permissions=True)
		if bot_user:
			frappe.db.set_value("Raven Message", message.name, "owner", bot_user, update_modified=False)
		polls[poll.name] = {"issue": ctx.doc.name, "field": item["field"], "values": values, "message": message.name}
	return list(polls)


# --- voting --------------------------------------------------------------------------------------


def on_poll_vote(doc, method=None):
	"""Raven Poll Vote after_insert, in the voter's request. Never blocks the vote."""
	try:
		apply_vote(doc)
	except Exception:
		frappe.log_error(title=f"Issue Assistant: poll vote on {doc.poll_id} failed")


def _poll_run(poll):
	"""The assistant's run that posted the poll, with its entry, or (None, None)."""
	message = frappe.db.get_value("Raven Message", {"poll_id": poll}, ["channel_id"], as_dict=True)
	channel = frappe.db.get_value("Raven Channel", message.channel_id, ["linked_doctype", "linked_document"],
		as_dict=True) if message else None
	if not channel or channel.linked_doctype != "Issue":
		return None, None
	for name in frappe.get_all("AI Agent Run", filters={"reference_doctype": "Issue",
			"reference_name": channel.linked_document, "analysis": ("like", f"%{poll}%")}, pluck="name"):
		run = frappe.get_doc("AI Agent Run", name)
		entry = ((frappe.parse_json(run.analysis or "{}") or {}).get("polls") or {}).get(poll)
		if entry:
			return run, entry
	return None, None


def apply_vote(vote):
	run, entry = _poll_run(vote.poll_id)
	if not entry:
		return None  # not the assistant's poll
	if entry.get("decided_by") or frappe.db.get_value("Raven Poll", vote.poll_id, "is_disabled"):
		return None  # decided already; Raven refuses votes on a closed poll, this covers a race
	voter = vote.user_id
	issue = entry["issue"]
	option = vote.vote_selection[0].option if vote.vote_selection else None
	if option not in entry["values"]:
		return None
	if not frappe.has_permission("Issue", "write", doc=issue, user=voter):
		if not entry.get("noted"):
			entry["noted"] = 1
			_save_entry(run, vote.poll_id, entry)
			_say(run, issue, _("Only someone who may change {0} decides here; {1}'s vote changes nothing.").format(
				issue, frappe.utils.get_fullname(voter)))
		return None
	value = entry["values"][option]
	name = frappe.utils.get_fullname(voter)
	_close(vote.poll_id)
	entry.update(decided_by=voter, decided=value)
	_save_entry(run, vote.poll_id, entry)
	if value == NONE:
		_say(run, issue, _("{0} chose none of these; nothing changed.").format(name))
		return None
	text = _apply(issue, entry["field"], value, voter)
	_say(run, issue, _("Set on {0}'s request: {1}").format(name, text))
	return value


def _apply(issue, field, value, voter):
	"""In the voter's session: their permissions decide (like #2116's chat answers)."""
	previous = frappe.session.user
	frappe.set_user(voter)
	try:
		if field == PERSON:
			if not frappe.db.exists("ToDo", {"reference_type": "Issue", "reference_name": issue, "allocated_to": value,
					"status": "Open"}):
				from frappe.desk.form.assign_to import add as assign_to

				assign_to({"assign_to": [value], "doctype": "Issue", "name": issue})
			return _("assigned {0}").format(frappe.utils.get_fullname(value))
		doc = frappe.get_doc("Issue", issue)
		doc.set(field, value)
		doc.save()
		return f"{_(doc.meta.get_label(field))} → {value}"
	finally:
		frappe.set_user(previous)


def _close(poll):
	frappe.db.set_value("Raven Poll", poll, "is_disabled", 1)
	frappe.clear_document_cache("Raven Poll", poll)
	from raven.api.raven_poll import publish_poll_update

	publish_poll_update(poll)


def _save_entry(run, poll, entry):
	analysis = frappe.parse_json(run.analysis or "{}") or {}
	analysis.setdefault("polls", {})[poll] = entry
	run.db_set("analysis", frappe.as_json(analysis), update_modified=False)


def _say(run, issue, text):
	"""A short line by the assistant's bot in the Issue chat."""
	from phamos.api.issue_chat import find_channel

	bot_name = frappe.db.get_value("AI Agent", run.agent, "raven_bot")
	channel = find_channel("Issue", issue)
	if not bot_name or not channel:
		return
	bot = frappe.get_doc("Raven Bot", bot_name)
	message = bot.send_message(channel.name, f"<p>{escape_html(text)}</p>")
	if bot.raven_user:
		frappe.db.set_value("Raven Message", message, "owner", bot.raven_user, update_modified=False)
