# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Ideas in the Personal Cockpit (phamos/phamos#1771): capture, write out, let them grow.

An Idea is a brain dump with a stage (Seed … Harvest, or Compost when set aside). Writing
sessions are recorded as Idea Writing Session rows; side ideas captured while writing become
child ideas (`spawned_from`).

Versioning as snapshots: autosave saves without a Version row. A row is written when the
title or stage changes, when the editor is left (`snapshot_idea`), when a session completes,
or when the content changed and the last snapshot is older than IDEA_SNAPSHOT_MINUTES. Each
row diffs against the previous snapshot, so the chain is complete but compact.

Ideas are private: every function works on the session user's own records only. The one
exception is the vote (#1842): an owner can hand an idea in, every cockpit user can then read it
(not its history or sessions) and upvote it once. Withdrawing or composting removes the votes.
"""

import html

import frappe
from frappe import _
from frappe.core.doctype.version.version import get_diff
from frappe.utils import add_to_date, cint, date_diff, get_datetime, now_datetime, today

from phamos.api.personal_focus import _minutes_between
from phamos.cockpits.defaults import (
	IDEA_AIM_FACTORS,
	IDEA_CLOSED_STAGES,
	IDEA_DEFAULT_WORD_BASE,
	IDEA_FEELINGS,
	IDEA_SNAPSHOT_MINUTES,
	IDEA_STAGE_JOBS,
	IDEA_STAGES,
	IDEA_TITLE_LENGTH,
	IDEA_VOTE_BLOCKED_STAGES,
	IDEA_VOTE_OPEN,
)

DOCTYPE = "Idea"
SESSION_DOCTYPE = "Idea Writing Session"
EVENT = "cockpit_idea_changed"
VOTE_DOCTYPE = "Idea Vote"
VOTE_EVENT = "cockpit_idea_vote_changed"
SETTINGS = "phamos Settings"
SNAPSHOT_FIELDS = ("title", "stage", "content")
LIST_FIELDS = [
	"name",
	"title",
	"stage",
	"summary",
	"spawned_from",
	"last_session_words",
	"harvested_on",
	"vote_status",
	"vote_count",
	"creation",
	"modified",
]
VOTE_FIELDS = ["name", "title", "summary", "stage", "user", "handed_in_on", "vote_count"]


# reading


def _age_days(creation):
	return max(0, date_diff(today(), get_datetime(creation).date()))


def _last_session(name):
	rows = frappe.get_all(
		SESSION_DOCTYPE,
		filters={"idea": name},
		fields=["started_on", "ended_on", "words_written", "duration_mins", "felt_productive"],
		order_by="started_on desc",
		limit=1,
	)
	return rows[0] if rows else None


def _serialize(doc):
	children = frappe.get_all(
		DOCTYPE,
		filters={"spawned_from": doc.name, "user": doc.user},
		fields=["name", "title", "stage"],
		order_by="creation asc",
	)
	return {
		"name": doc.name,
		"title": doc.title,
		"stage": doc.stage,
		"stage_job": IDEA_STAGE_JOBS.get(doc.stage, ""),
		"content": doc.content or "",
		"summary": doc.summary or "",
		"spawned_from": doc.spawned_from,
		"spawned_from_title": frappe.db.get_value(DOCTYPE, doc.spawned_from, "title") if doc.spawned_from else None,
		"last_session_words": cint(doc.last_session_words),
		"harvested_on": doc.harvested_on,
		"vote_status": doc.vote_status or "",
		"vote_count": cint(doc.vote_count),
		"handed_in_on": str(doc.handed_in_on) if doc.handed_in_on else None,
		"creation": str(doc.creation),
		"modified": str(doc.modified),
		"age_days": _age_days(doc.creation),
		"children": children,
		"last_session": _last_session(doc.name),
		"sessions_count": frappe.db.count(SESSION_DOCTYPE, {"idea": doc.name}),
	}


def get_ideas(stage=None, include_closed=0):
	"""My ideas, recently edited first. Harvest and Compost only on request or by stage filter."""
	filters = {"user": frappe.session.user}
	if stage:
		if stage not in IDEA_STAGES:
			frappe.throw(_("Unknown stage: {0}").format(stage))
		filters["stage"] = stage
	elif not cint(include_closed):
		filters["stage"] = ("not in", IDEA_CLOSED_STAGES)
	rows = frappe.get_all(DOCTYPE, filters=filters, fields=LIST_FIELDS, order_by="modified desc")
	if not rows:
		return []
	names = [row.name for row in rows]
	children = frappe.get_all(
		DOCTYPE,
		filters={"spawned_from": ("in", names), "user": frappe.session.user},
		fields=["spawned_from", "count(name) as count"],
		group_by="spawned_from",
	)
	counts = {row.spawned_from: row.count for row in children}
	parents = {row.spawned_from for row in rows if row.spawned_from}
	titles = (
		dict(frappe.get_all(DOCTYPE, filters={"name": ("in", list(parents))}, fields=["name", "title"], as_list=True))
		if parents
		else {}
	)
	for row in rows:
		row["children_count"] = counts.get(row.name, 0)
		row["spawned_from_title"] = titles.get(row.spawned_from)
		row["age_days"] = _age_days(row.creation)
		row["creation"] = str(row.creation)
		row["modified"] = str(row.modified)
	return rows


def get_idea(name):
	return _serialize(_get_my_idea(name))


def get_idea_options():
	return {
		"stages": list(IDEA_STAGES),
		"closed_stages": list(IDEA_CLOSED_STAGES),
		"jobs": IDEA_STAGE_JOBS,
		"feelings": list(IDEA_FEELINGS),
		"default_word_base": IDEA_DEFAULT_WORD_BASE,
	}


def word_goal(name, aim_choice="similar"):
	"""Words to aim for in the next session: the last session's words (or the default base) scaled by the aim."""
	doc = _get_my_idea(name)
	return _word_goal(doc.last_session_words, aim_choice)


def _word_goal(last_words, aim_choice):
	if aim_choice not in IDEA_AIM_FACTORS:
		frappe.throw(_("Unknown aim: {0}").format(aim_choice))
	base = cint(last_words) or IDEA_DEFAULT_WORD_BASE
	return round(base * IDEA_AIM_FACTORS[aim_choice])


# writing


def _get_my_idea(name):
	if not name or not frappe.db.exists(DOCTYPE, name):
		frappe.throw(_("Idea {0} not found").format(name), frappe.DoesNotExistError)
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.user != frappe.session.user:
		frappe.throw(_("This idea is not yours."), frappe.PermissionError)
	return doc


def _publish(doc):
	frappe.publish_realtime(
		EVENT, {"name": doc.name, "modified": str(doc.modified)}, user=doc.user, after_commit=True
	)


def _snapshot_due(doc):
	if (doc.title or "") != (doc.snapshot_title or "") or (doc.stage or "") != (doc.snapshot_stage or ""):
		return True
	if (doc.content or "") == (doc.snapshot_content or ""):
		return False
	if not doc.last_snapshot_on:
		return True
	return now_datetime() >= add_to_date(get_datetime(doc.last_snapshot_on), minutes=IDEA_SNAPSHOT_MINUTES)


def _snapshot(doc, force=False):
	"""Write a Version row from the previous snapshot to the current state, when something changed."""
	# Two calls at once (blur and route leave) must not both write the same step: lock the row and
	# read the snapshot fields again under the lock.
	frappe.db.get_value(DOCTYPE, doc.name, "name", for_update=True)
	doc.update(
		frappe.db.get_value(
			DOCTYPE, doc.name, [f"snapshot_{f}" for f in SNAPSHOT_FIELDS] + ["last_snapshot_on"], as_dict=True
		)
	)
	if not force and not _snapshot_due(doc):
		return False
	old = frappe.copy_doc(doc, ignore_no_copy=False)
	old.name = doc.name
	for field in SNAPSHOT_FIELDS:
		old.set(field, doc.get(f"snapshot_{field}"))
	written = False
	diff = get_diff(old, doc)
	if diff:
		# Only what the snapshot tracks; derived fields (summary, counters) are noise in the history.
		diff.changed = [row for row in diff.changed if row[0] in SNAPSHOT_FIELDS]
	if diff and diff.changed:
		version = frappe.new_doc("Version")
		version.ref_doctype = DOCTYPE
		version.docname = doc.name
		version.data = frappe.as_json(diff, indent=None, separators=(",", ":"))
		version.insert(ignore_permissions=True)
		written = True
	values = {f"snapshot_{field}": doc.get(field) for field in SNAPSHOT_FIELDS}
	values["last_snapshot_on"] = now_datetime()
	doc.db_set(values, update_modified=False)
	return written


def create_idea(title=None, content=None, spawned_from=None):
	if spawned_from:
		_get_my_idea(spawned_from)
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"user": frappe.session.user,
			"title": title,
			"content": content,
			"spawned_from": spawned_from or None,
			"stage": "Seed",
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	_snapshot(doc, force=True)  # the first row of the history: from nothing to the captured idea
	_publish(doc)
	return _serialize(doc)


def update_idea(name, title=None, content=None, stage=None, modified=None):
	"""Autosave target: None leaves a field untouched. A stale `modified` raises TimestampMismatchError."""
	doc = _get_my_idea(name)
	if title is not None:
		title = title.strip()
		if not title:
			frappe.throw(_("Title is required"))
		doc.title = title[:IDEA_TITLE_LENGTH]
	if content is not None:
		doc.content = content
	if stage is not None:
		if stage not in IDEA_STAGES:
			frappe.throw(_("Unknown stage: {0}").format(stage))
		doc.stage = stage
	if modified:
		doc.modified = get_datetime(modified)
	was_open = doc.vote_status == IDEA_VOTE_OPEN
	doc.flags.ignore_permissions = True
	doc.save(ignore_version=True)
	_snapshot(doc)
	_publish(doc)
	if was_open and not doc.vote_status:  # composted: it left the vote
		_publish_vote(doc.name, 0, "")
	return _serialize(doc)


def snapshot_idea(name):
	"""The editor was left: close the open edit as one Version row (none if nothing changed)."""
	doc = _get_my_idea(name)
	return {"written": _snapshot(doc, force=True)}


def complete_writing_session(
	name, started_on, words_written, word_goal, aim_choice, felt_productive="", content=None
):
	doc = _get_my_idea(name)
	if aim_choice not in IDEA_AIM_FACTORS:
		frappe.throw(_("Unknown aim: {0}").format(aim_choice))
	if felt_productive and felt_productive not in IDEA_FEELINGS:
		frappe.throw(_("Unknown feeling: {0}").format(felt_productive))
	started = get_datetime(started_on)
	ended = now_datetime()
	if not started or started > ended:
		frappe.throw(_("The session cannot start in the future."))
	words = max(0, cint(words_written))

	if content is not None:
		doc.content = content
	doc.last_session_words = words
	doc.flags.ignore_permissions = True
	doc.save(ignore_version=True)

	session = frappe.get_doc(
		{
			"doctype": SESSION_DOCTYPE,
			"user": frappe.session.user,
			"idea": doc.name,
			"started_on": started,
			"ended_on": ended,
			"duration_mins": _minutes_between(started, ended),
			"words_written": words,
			"word_goal": max(0, cint(word_goal)),
			"aim_choice": aim_choice,
			"felt_productive": felt_productive or None,
		}
	)
	session.insert(ignore_permissions=True)
	_snapshot(doc, force=True)
	_publish(doc)
	return {
		"idea": _serialize(doc),
		"session": {
			"name": session.name,
			"duration_mins": session.duration_mins,
			"words_written": session.words_written,
		},
	}


def _text_to_html(text):
	return "".join(f"<p>{html.escape(line)}</p>" for line in text.splitlines() if line.strip())


def capture_side_idea(parent, text, name=None):
	"""A thought caught while writing becomes a child idea; the first line is its title.

	With `name` the same child is updated as the user keeps typing. Empty text changes nothing.
	"""
	parent_doc = _get_my_idea(parent)
	text = (text or "").strip()
	if not text:
		return None
	title = next(line.strip() for line in text.splitlines() if line.strip())[:IDEA_TITLE_LENGTH]
	if name:
		doc = _get_my_idea(name)
		if doc.spawned_from != parent_doc.name:
			frappe.throw(_("This idea did not come from {0}.").format(parent_doc.title))
		doc.title = title
		doc.content = _text_to_html(text)
		doc.flags.ignore_permissions = True
		doc.save(ignore_version=True)
		_snapshot(doc)
		_publish(doc)
		return _serialize(doc)
	return create_idea(title=title, content=_text_to_html(text), spawned_from=parent_doc.name)


# vote (#1842)


def _publish_vote(name, vote_count, vote_status):
	"""Tell every open vote list; the payload carries no content, the list reloads through the API."""
	frappe.publish_realtime(
		VOTE_EVENT,
		{"name": name, "vote_count": cint(vote_count), "vote_status": vote_status or ""},
		after_commit=True,
	)


def _show_author():
	# The patch set_personal_ideas_show_author_default stores the default (on) on existing sites.
	return bool(cint(frappe.db.get_single_value(SETTINGS, "personal_ideas_show_author")))


def _authors(users):
	if not users or not _show_author():
		return {}
	rows = frappe.get_all(
		"User",
		filters={"name": ("in", list(users))},
		fields=["name", "full_name", "user_image"],
		ignore_permissions=True,
	)
	return {row.name: {"name": row.name, "full_name": row.full_name or row.name, "user_image": row.user_image} for row in rows}


def _require_cockpit_user():
	"""Ideas up for vote are for colleagues: System Users only, as the Personal Cockpit itself.

	Whitelisted methods are callable by any logged-in user, Website Users (portal customers)
	included, and these read other people's ideas, so the check has to be here.
	"""
	user = frappe.session.user
	if user in (None, "Guest") or (
		user != "Administrator" and frappe.get_cached_value("User", user, "user_type") != "System User"
	):
		frappe.throw(_("Only colleagues can see ideas up for vote."), frappe.PermissionError)


def _open_idea(name):
	"""An idea open for vote (anyone's), or my own; anything else is not there for this user."""
	_require_cockpit_user()
	row = frappe.db.get_value(DOCTYPE, name, ["user", "vote_status"], as_dict=True) if name else None
	if not row:
		frappe.throw(_("Idea {0} not found").format(name), frappe.DoesNotExistError)
	if row.vote_status != IDEA_VOTE_OPEN and row.user != frappe.session.user:
		frappe.throw(_("This idea is not open for a vote."), frappe.PermissionError)
	return frappe.get_doc(DOCTYPE, name)


def _vote_row(doc, voted, authors):
	return {
		"name": doc.name,
		"title": doc.title,
		"summary": doc.summary or "",
		"stage": doc.stage,
		"handed_in_on": str(doc.handed_in_on) if doc.handed_in_on else None,
		"vote_status": doc.vote_status or "",
		"vote_count": cint(doc.vote_count),
		"mine": doc.user == frappe.session.user,
		"voted": voted,
		"author": authors.get(doc.user),
	}


def hand_in_idea_for_vote(name):
	"""Open my idea for a vote: every cockpit user can read it and vote for it."""
	doc = _get_my_idea(name)
	if doc.stage in IDEA_VOTE_BLOCKED_STAGES:
		frappe.throw(_("A composted idea cannot be handed in. Take it up again first."))
	if doc.vote_status != IDEA_VOTE_OPEN:
		doc.vote_status = IDEA_VOTE_OPEN
		doc.flags.ignore_permissions = True
		doc.save(ignore_version=True)
		_publish(doc)
		_publish_vote(doc.name, doc.vote_count, doc.vote_status)
	return _serialize(doc)


def withdraw_idea_from_vote(name):
	"""Make my idea private again; the votes so far are removed (Idea.on_update)."""
	doc = _get_my_idea(name)
	if doc.vote_status:
		doc.vote_status = ""
		doc.flags.ignore_permissions = True
		doc.save(ignore_version=True)
		doc.reload()
		_publish(doc)
		_publish_vote(doc.name, 0, "")
	return _serialize(doc)


def get_ideas_for_vote():
	"""Every idea open for vote, most votes first; with my vote and, if the setting allows, the author."""
	_require_cockpit_user()
	rows = frappe.get_all(
		DOCTYPE,
		filters={"vote_status": IDEA_VOTE_OPEN},
		fields=VOTE_FIELDS,
		order_by="vote_count desc, handed_in_on desc",
		ignore_permissions=True,
	)
	if not rows:
		return []
	me = frappe.session.user
	voted = set(
		frappe.get_all(
			VOTE_DOCTYPE,
			filters={"user": me, "idea": ("in", [row.name for row in rows])},
			pluck="idea",
			ignore_permissions=True,
		)
	)
	authors = _authors({row.user for row in rows})
	return [_vote_row(row, row.name in voted, authors) for row in rows]


def get_idea_for_vote(name):
	"""The voter's view of one idea: its text and the vote, not its history, sessions or children."""
	doc = _open_idea(name)
	if doc.vote_status != IDEA_VOTE_OPEN:
		frappe.throw(_("This idea is not open for a vote."), frappe.PermissionError)
	voted = bool(frappe.db.exists(VOTE_DOCTYPE, {"idea": doc.name, "user": frappe.session.user}))
	row = _vote_row(doc, voted, _authors({doc.user}))
	row["content"] = doc.content or ""
	return row


def vote_idea(name):
	"""Toggle my upvote on someone else's idea open for vote. Returns {name, voted, vote_count}."""
	doc = _open_idea(name)
	me = frappe.session.user
	if doc.user == me:
		frappe.throw(_("You cannot vote for your own idea."), frappe.PermissionError)
	# Lock the idea so two votes at once count right, and read the status under the lock: a
	# withdraw at the same moment must not leave a vote behind.
	if frappe.db.get_value(DOCTYPE, doc.name, "vote_status", for_update=True) != IDEA_VOTE_OPEN:
		frappe.throw(_("This idea is not open for a vote."), frappe.PermissionError)
	existing = frappe.db.get_value(VOTE_DOCTYPE, {"idea": doc.name, "user": me})
	if existing:
		frappe.delete_doc(VOTE_DOCTYPE, existing, ignore_permissions=True, force=True)
		voted = False
	else:
		frappe.get_doc({"doctype": VOTE_DOCTYPE, "idea": doc.name, "user": me}).insert(ignore_permissions=True)
		voted = True
	count = frappe.db.count(VOTE_DOCTYPE, {"idea": doc.name})
	# Not `modified`: a vote must not trip the owner's autosave lock.
	frappe.db.set_value(DOCTYPE, doc.name, "vote_count", count, update_modified=False)
	_publish_vote(doc.name, count, IDEA_VOTE_OPEN)
	return {"name": doc.name, "voted": voted, "vote_count": count}
