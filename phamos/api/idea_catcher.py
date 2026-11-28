# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Idea Catcher (phamos/phamos#2200): catch an idea on the phone in one step, link it afterwards.

The page is phamos/www/idea.html. Every function works on the session user's own ideas only,
through the Personal Cockpit's idea logic (phamos.api.personal_ideas).

- save_idea: the captured text becomes a new Idea (Seed, title from its first words).
- search_my_ideas / suggest_ideas: candidates to link the new idea to. Suggestions compare the
  texts with Mistral embeddings (#2206); off unless Cockpit Settings turns them on.
- link_idea: "spawned" sets the new idea's spawned_from; "append" adds its text to the chosen
  idea and deletes the new one (undo_append takes that back, #2209).
- add_to_idea: a thought added to one of my ideas from its page in the app (#2210). Reading,
  editing, growing and voting use the Personal Cockpit's endpoints (phamos.api.personal_cockpit).
"""

import math

import frappe
from frappe import _
from frappe.utils import cint, cstr, format_datetime, now_datetime

from phamos.ai_agents import llm
from phamos.api import personal_ideas
from phamos.cockpits.defaults import IDEA_CLOSED_STAGES, IDEA_TITLE_LENGTH
from phamos.cockpits.permissions import is_colleague
from phamos.cockpits.settings import COCKPIT_SETTINGS
from phamos.cockpits.doctype.idea.idea import excerpt

DOCTYPE = "Idea"
TITLE_WORDS = 8
MAX_TEXT = 20000  # characters; longer texts belong in the Personal Cockpit's editor
CLIENT_ID_TTL = 7 * 24 * 3600  # an offline phone resends within a week at most
LINK_MODES = ("spawned", "append")
UNDO_SECONDS = 60  # the page offers Undo for 8 seconds; the rest is slack for a slow network
SEARCH_LIMIT = 20
# Nearby ideas (#2206)
SUGGEST_CANDIDATES = 60  # my most recently changed open ideas that are compared
SUGGEST_LIMIT = 5
EMBED_TEXT_LENGTH = 2000
EMBED_BATCH = 16  # texts per request: 16 × ~500 tokens stays below Mistral's per-request limit
EMBED_CACHE_TTL = 30 * 24 * 3600
# Cosine similarity of mistral-embed vectors: unrelated texts still score around 0.6.
BANDS = ((0.86, "very close"), (0.78, "related"))
MIN_SCORE = 0.7


def require_user():
	"""Colleagues only (System Users), as the Personal Cockpit: ideas are an employee's own notes."""
	if not is_colleague():
		frappe.throw(_("Only colleagues can catch ideas."), frappe.PermissionError)


def title_from_text(text):
	"""The first words of the first line, so catching needs no title."""
	first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
	words = first_line.split()
	title = " ".join(words[:TITLE_WORDS])
	if len(words) > TITLE_WORDS:
		title += " …"
	return title[:IDEA_TITLE_LENGTH]


def _client_key(client_id):
	return f"phamos:idea_catcher:{frappe.session.user}:{client_id}"


def _short(name):
	doc = frappe.db.get_value(DOCTYPE, name, ["name", "title", "summary", "stage", "modified"], as_dict=True)
	return {**doc, "modified": str(doc.modified)} if doc else None


@frappe.whitelist(methods=["POST"])
def save_idea(text, client_id=None):
	"""Store the caught text as a new Idea of mine.

	`client_id` is made by the phone for each idea; sending the same one again (an offline queue
	retrying after a lost answer) returns the idea already made instead of a second one.
	"""
	require_user()
	text = cstr(text).strip()
	if not text:
		frappe.throw(_("Write or dictate your idea first."))
	if len(text) > MAX_TEXT:
		frappe.throw(_("That is too long for a quick idea. Write it out in the Personal Cockpit."))
	client_id = cstr(client_id).strip()[:64]
	if client_id:
		known = frappe.cache().get_value(_client_key(client_id), expires=True)
		if known and frappe.db.exists(DOCTYPE, {"name": known, "user": frappe.session.user}):
			return {**_short(known), "duplicate": True}
	idea = personal_ideas.create_idea(
		title=title_from_text(text), content=personal_ideas._text_to_html(text)
	)
	if client_id:
		frappe.cache().set_value(_client_key(client_id), idea["name"], expires_in_sec=CLIENT_ID_TTL)
	return _short(idea["name"])


@frappe.whitelist()
def search_my_ideas(query=None, exclude=None):
	"""My open ideas, recently changed first; `query` narrows by title and summary."""
	require_user()
	filters = {"user": frappe.session.user, "stage": ("not in", IDEA_CLOSED_STAGES)}
	if exclude:
		filters["name"] = ("!=", exclude)
	or_filters = None
	query = cstr(query).strip()
	if query:
		like = f"%{query}%"
		or_filters = {"title": ("like", like), "summary": ("like", like)}
	rows = frappe.get_all(
		DOCTYPE,
		filters=filters,
		or_filters=or_filters,
		fields=["name", "title", "summary", "stage", "modified"],
		order_by="modified desc",
		limit=SEARCH_LIMIT,
	)
	for row in rows:
		row["modified"] = str(row.modified)
	return rows


def ai_suggestions_enabled():
	return bool(cint(frappe.db.get_single_value(COCKPIT_SETTINGS, "personal_ideas_ai_suggestions")))


def _embed_text(row):
	return f"{row.title}\n{excerpt(row.content, EMBED_TEXT_LENGTH)}"


def _embeddings(rows):
	"""Vectors of the ideas, cached per idea and modified time so each text is sent only once."""
	cache = frappe.cache()
	keys = [f"phamos:idea_embedding:{row.name}:{row.modified}" for row in rows]
	vectors = [cache.get_value(key, expires=True) for key in keys]
	missing = [i for i, vector in enumerate(vectors) if not vector]
	# In batches, so one request stays below Mistral's token limit per call, and what was
	# fetched is cached even if a later batch fails.
	for start in range(0, len(missing), EMBED_BATCH):
		batch = missing[start : start + EMBED_BATCH]
		fresh = llm.embed([_embed_text(rows[i]) for i in batch])
		if len(fresh) != len(batch):
			raise ValueError(f"Mistral returned {len(fresh)} embeddings for {len(batch)} texts")
		for i, vector in zip(batch, fresh):
			vectors[i] = vector
			cache.set_value(keys[i], vector, expires_in_sec=EMBED_CACHE_TTL)
	return vectors


def _cosine(a, b):
	dot = sum(x * y for x, y in zip(a, b))
	norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
	return dot / norm if norm else 0.0


def _band(score):
	return next((label for limit, label in BANDS if score >= limit), "far")


@frappe.whitelist()
def suggest_ideas(name):
	"""My ideas nearest to idea `name`, by meaning (#2206). Only my own ideas are compared.

	Returns {"enabled": bool, "ideas": [... with score and band], "error": message or None}.
	"""
	require_user()
	doc = personal_ideas._get_my_idea(name)
	if not ai_suggestions_enabled() or not llm.get_mistral_settings():
		return {"enabled": False, "ideas": [], "error": None}
	candidates = frappe.get_all(
		DOCTYPE,
		filters={
			"user": frappe.session.user,
			"name": ("!=", doc.name),
			"stage": ("not in", IDEA_CLOSED_STAGES),
		},
		fields=["name", "title", "summary", "content", "stage", "modified"],
		order_by="modified desc",
		limit=SUGGEST_CANDIDATES,
	)
	if not candidates:
		return {"enabled": True, "ideas": [], "error": None}
	try:
		me = frappe._dict(name=doc.name, title=doc.title, content=doc.content, modified=doc.modified)
		vectors = _embeddings([me, *candidates])
	except Exception:
		frappe.log_error(title=_("Idea suggestions failed"), message=frappe.get_traceback())
		return {"enabled": True, "ideas": [], "error": _("The AI could not be asked. Search instead.")}
	scored = []
	for row, vector in zip(candidates, vectors[1:]):
		score = _cosine(vectors[0], vector)
		if score < MIN_SCORE:
			continue
		scored.append(
			{
				"name": row.name,
				"title": row.title,
				"summary": row.summary,
				"stage": row.stage,
				"modified": str(row.modified),
				"score": round(score, 3),
				"band": _band(score),
			}
		)
	scored.sort(key=lambda row: row["score"], reverse=True)
	return {"enabled": True, "ideas": scored[:SUGGEST_LIMIT], "error": None}


def _ancestors(name, limit=50):
	"""Names of the ideas `name` grew out of, nearest first (bounded, in case of old loops)."""
	seen = []
	parent = frappe.db.get_value(DOCTYPE, name, "spawned_from")
	while parent and parent not in seen and len(seen) < limit:
		seen.append(parent)
		parent = frappe.db.get_value(DOCTYPE, parent, "spawned_from")
	return seen


@frappe.whitelist(methods=["POST"])
def link_idea(name, target, mode):
	"""Tie the caught idea `name` to my idea `target`.

	spawned: `name` grew out of `target` (spawned_from).
	append: the text of `name` is added to `target` under a date line, and `name` is deleted.
	"""
	require_user()
	if mode not in LINK_MODES:
		frappe.throw(_("Unknown link: {0}").format(mode))
	doc = personal_ideas._get_my_idea(name)
	target_doc = personal_ideas._get_my_idea(target)
	if doc.name == target_doc.name:
		frappe.throw(_("An idea cannot come from itself."))
	if mode == "spawned":
		if doc.name in _ancestors(target_doc.name):
			frappe.throw(_("{0} already grew out of this idea.").format(target_doc.title))
		doc.spawned_from = target_doc.name
		doc.flags.ignore_permissions = True
		doc.save(ignore_version=True)
		personal_ideas._publish(doc)
		return {"name": doc.name, "target": _short(target_doc.name)}

	# Only a fresh catch is merged away: an idea someone wrote on or handed in for a vote keeps
	# its history, sessions and votes, so it can only be linked.
	if (
		doc.stage != "Seed"
		or doc.vote_status
		or frappe.db.exists("Idea Writing Session", {"idea": doc.name})
	):
		frappe.throw(_("This idea has its own history. Link it instead of adding it."))
	# Its children move to the target below; a target that grew out of it (at any depth) would
	# then point at itself or close a loop.
	if doc.name in _ancestors(target_doc.name):
		frappe.throw(_("{0} grew out of this idea. Link it instead of adding it.").format(target_doc.title))
	content_before = target_doc.content or ""
	_append(target_doc, doc.content or "")
	# The caught idea lived only as long as it took to choose; its text now lives in the target.
	# Ideas that grew out of it now grew out of the target (on_trash would otherwise unlink them).
	children = frappe.get_all(DOCTYPE, filters={"spawned_from": doc.name}, pluck="name")
	frappe.db.set_value(
		DOCTYPE, {"spawned_from": doc.name}, "spawned_from", target_doc.name, update_modified=False
	)
	caught = doc.as_dict(no_default_fields=True)
	frappe.delete_doc(DOCTYPE, doc.name, ignore_permissions=True, force=True)
	# Undo (#2209): what it takes to put both ideas back, for a short while.
	token = frappe.generate_hash(length=16)
	frappe.cache().set_value(
		_undo_key(token),
		{
			"caught": {**caught, "name": doc.name},
			"children": children,
			"target": target_doc.name,
			"content_before": content_before,
			"modified_after": str(frappe.db.get_value(DOCTYPE, target_doc.name, "modified")),
		},
		expires_in_sec=UNDO_SECONDS,
	)
	return {"name": None, "target": _short(target_doc.name), "undo": token}


def _append(doc, html):
	"""Add `html` at the bottom of my idea under an "Added <date and time>" line, and save it."""
	stamp = format_datetime(now_datetime())  # the user's own date and time format
	doc.content = (doc.content or "") + f"<p><em>{_('Added {0}').format(stamp)}</em></p>{html}"
	doc.flags.ignore_permissions = True
	doc.save(ignore_version=True)
	personal_ideas._snapshot(doc, force=True)
	personal_ideas._publish(doc)


@frappe.whitelist(methods=["POST"])
def add_to_idea(name, text):
	"""Add a thought to one of my ideas from the app's idea page (#2210), as "Add to it" does."""
	require_user()
	text = cstr(text).strip()
	if not text:
		frappe.throw(_("Write or dictate your idea first."))
	if len(text) > MAX_TEXT:
		frappe.throw(_("That is too long for a quick idea. Write it out in the Personal Cockpit."))
	doc = personal_ideas._get_my_idea(name)
	_append(doc, personal_ideas._text_to_html(text))
	return personal_ideas._serialize(doc)


def _undo_key(token):
	return f"phamos:idea_catcher:undo:{frappe.session.user}:{token}"


@frappe.whitelist(methods=["POST"])
def undo_append(token):
	"""Take back an "Add to it" (#2209): the target gets its text back, the caught idea returns
	under its old name, and ideas that grew out of it point at it again.

	Only within UNDO_SECONDS, only by the same user, and only while the target is unchanged
	since (an edit elsewhere would otherwise be lost).
	"""
	require_user()
	key = _undo_key(cstr(token)[:32])
	data = frappe.cache().get_value(key, expires=True)
	if not data:
		frappe.throw(_("Too late to undo. Change the idea in the Personal Cockpit instead."))
	target_doc = personal_ideas._get_my_idea(data["target"])
	if str(target_doc.modified) != data["modified_after"]:
		frappe.throw(_("{0} was changed in the meantime, so this cannot be undone.").format(target_doc.title))
	frappe.cache().delete_value(key)

	target_doc.content = data["content_before"]
	target_doc.flags.ignore_permissions = True
	target_doc.save(ignore_version=True)
	personal_ideas._snapshot(target_doc, force=True)
	personal_ideas._publish(target_doc)

	caught = frappe.get_doc({**data["caught"], "doctype": DOCTYPE})
	caught.flags.ignore_permissions = True
	caught.insert(set_name=data["caught"]["name"])
	personal_ideas._publish(caught)
	if data["children"]:
		frappe.db.set_value(
			DOCTYPE,
			{"name": ("in", data["children"]), "spawned_from": target_doc.name},
			"spawned_from",
			caught.name,
			update_modified=False,
		)
	return _short(caught.name)
