# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Learn from people correcting an AI agent: the parts every agent shares (#2225).

An agent's handler module says what counts as a correction on its documents; this module
- finds the latest completed run of the agent on a document,
- stores the corrections on that run (outcome Corrected, who corrected, when),
- creates a *suggested* AI Skill from a correction, or counts the same suggestion again
  (same `suggestion_key` → `occurrences` + 1; a dismissed one is never made again),
- accepts and dismisses suggestions,
- marks runs Accepted that nobody corrected for a while, and counts rates.

Nothing a suggestion says applies until a person accepts it, and no AI agent's user may accept
one. Moved out of the Accounting loop (phamos/accounting/feedback.py), which uses it too.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, now_datetime

SUGGESTED, LEARNED = "Suggested", "Learned"
# runs that answered someone in a chat (#2116) set what that person asked for: they are no AI judgement to
# learn from, so the loop leaves them out (local test of #2226, 2026-11-28)
NOT_LEARNED_FROM = ("Chat",)
ACCEPTED, CORRECTED = "Accepted", "Corrected"


def ai_users():
	"""The users of all AI agents: their changes never count as corrections, and they never accept. Read once
	per request: the Issue and ToDo hooks ask on every save (AI review on !1392)."""
	if frappe.flags.ai_agent_users is None:
		frappe.flags.ai_agent_users = set(frappe.get_all("AI Agent", filters={"user": ("is", "set")}, pluck="user"))
	return frappe.flags.ai_agent_users


def is_ai_user(user):
	return bool(user) and user in ai_users()


def latest_run(agent, doctype, name):
	"""The agent's latest completed run on the document, or None."""
	run = frappe.db.get_value("AI Agent Run", {"agent": agent, "reference_doctype": doctype,
		"reference_name": name, "status": "Completed", "trigger": ("not in", NOT_LEARNED_FROM)}, "name",
		order_by="creation desc")
	return frappe.get_doc("AI Agent Run", run) if run else None


def record(run, found, user, done=False, keep_accepted=False, corrector_of_new=False):
	"""Store the corrections `found` ([{field, ai_value, human_value, ...}]) on the run. Returns the ones
	that are new since the last time (a field first corrected now, or corrected to another value).

	A correction keeps its first user and time while its value stays. No corrections: the run is Accepted
	when `done`, else open. The defaults keep the Accounting loop as it was; the Issue Assistant keeps an
	Accepted from its daily job (`keep_accepted`) and names who made the newest correction, not whoever
	saved last (`corrector_of_new`). Nothing is written when nothing changed."""
	previous = {c["field"]: c for c in frappe.parse_json(run.corrections or "[]") or []}
	now = now_datetime()
	for c in found:
		old = previous.get(c["field"])
		same = old and old.get("human_value") == c["human_value"]
		c["user"] = old.get("user") if same else user
		c["at"] = old.get("at") if same else str(now)
	new = [c for c in found if c["field"] not in previous or previous[c["field"]].get("human_value") != c["human_value"]]
	values = {"corrections": frappe.as_json(found) if found else None}
	if found:
		corrector = (new[0]["user"] if new else run.corrected_by or user) if corrector_of_new else user
		values.update(outcome=CORRECTED, corrected_by=corrector)
	elif done or (keep_accepted and run.outcome == ACCEPTED):
		values.update(outcome=ACCEPTED, corrected_by=None)
	else:
		values.update(outcome=None, corrected_by=None)
	before = {"corrections": frappe.parse_json(run.corrections or "null") or None, "outcome": run.outcome or None,
		"corrected_by": run.corrected_by or None}
	after = {"corrections": found or None, "outcome": values["outcome"], "corrected_by": values["corrected_by"]}
	if before != after or not run.feedback_collected_at:
		values["feedback_collected_at"] = now
		run.db_set(values, update_modified=False)
	return new


def suggestion(key, run, make):
	"""The suggestion with this key: counted again when it exists (unless dismissed or already accepted),
	else created by `make()` (an AI Skill dict, inserted here as origin Suggested and disabled)."""
	existing = frappe.db.get_value("AI Skill", {"suggestion_key": key},
		["name", "dismissed", "occurrences", "origin"], as_dict=True)
	if existing:
		if not existing.dismissed and existing.origin == SUGGESTED:
			frappe.db.set_value("AI Skill", existing.name, {"occurrences": cint(existing.occurrences) + 1,
				"source_run": run.name})
		return existing.name
	values = make()
	if not values:
		return None
	skill = frappe.get_doc({"doctype": "AI Skill", "agent": run.agent, "enabled": 0, "origin": SUGGESTED,
		"occurrences": 1, "source_run": run.name, "suggestion_key": key, **values})
	skill.insert(ignore_permissions=True)
	return skill.name


def _suggested(name):
	if is_ai_user(frappe.session.user):
		# an agent never approves what it suggested itself (#2225 decision 5)
		frappe.throw(_("An AI agent can't accept or dismiss suggestions."), frappe.PermissionError)
	skill = frappe.get_doc("AI Skill", name)
	skill.check_permission("write")
	if skill.origin != SUGGESTED:
		frappe.throw(_("{0} is not a suggestion.").format(name))
	return skill


def accept_suggestion(name):
	skill = _suggested(name)
	skill.update({"enabled": 1, "origin": LEARNED, "dismissed": 0})
	skill.save()
	return skill.name


def dismiss_suggestion(name):
	skill = _suggested(name)
	skill.update({"dismissed": 1, "enabled": 0})
	skill.save()
	return skill.name


def mark_accepted(agent, days, closed=None):
	"""Runs of the agent nobody corrected within `days` after they finished become Accepted; so do runs on
	documents `closed(doctype, names)` names as done. Returns how many were marked."""
	runs = frappe.get_all("AI Agent Run", filters={"agent": agent, "status": "Completed", "outcome": ("in", ("", None)),
		"trigger": ("not in", NOT_LEARNED_FROM)},
		fields=["name", "reference_doctype", "reference_name", "finished_at", "creation"], limit_page_length=5000)
	if not runs:
		return 0
	cutoff = add_days(now_datetime(), -cint(days))
	done = set()
	if closed:
		by_doctype = {}
		for r in runs:
			by_doctype.setdefault(r.reference_doctype, []).append(r.reference_name)
		for doctype, names in by_doctype.items():
			done |= {(doctype, n) for n in closed(doctype, names)}
	marked = 0
	for r in runs:
		if (r.finished_at or r.creation) <= cutoff or (r.reference_doctype, r.reference_name) in done:
			frappe.db.set_value("AI Agent Run", r.name, {"outcome": ACCEPTED, "feedback_collected_at": now_datetime()},
				update_modified=False)
			marked += 1
	return marked


def rates(agent, days, groups=None):
	"""How often people corrected what the agent set, over the last `days`:
	{"runs", "corrected_runs", "fields": {field: {"set", "corrected"}}, "groups": {group: {"set", "corrected"}}}.
	`groups` maps a field to the step it belongs to (e.g. identify, classify, person)."""
	rows = frappe.get_all("AI Agent Run", filters={"agent": agent, "status": "Completed",
		"trigger": ("not in", NOT_LEARNED_FROM),
		"creation": (">=", add_days(now_datetime(), -cint(days)))}, fields=["fields_set", "corrections", "outcome"],
		limit_page_length=10000)
	fields = {}
	for row in rows:
		corrected = {c.get("field") for c in frappe.parse_json(row.corrections or "[]") or []}
		for field in {f.strip() for f in cstr(row.fields_set).split(",") if f.strip()} | corrected:
			entry = fields.setdefault(field, {"set": 0, "corrected": 0})
			entry["set"] += 1
			entry["corrected"] += 1 if field in corrected else 0
	grouped = {}
	for field, entry in fields.items():
		group = (groups or {}).get(field, field)
		total = grouped.setdefault(group, {"set": 0, "corrected": 0})
		total["set"] += entry["set"]
		total["corrected"] += entry["corrected"]
	return {"runs": len(rows), "corrected_runs": sum(1 for r in rows if r.outcome == CORRECTED),
		"fields": fields, "groups": grouped, "days": cint(days)}
