# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Import ideas from a NextChapter site (phamos/phamos#1776).

NextChapter (phamos-eu/next-chapter) keeps ideas as "Implementation Chapter" and sessions as
"Writing Session". A chapter has no user field; its author is the record owner. This form signs
in with a username and password, lists the NextChapter accounts for a mapping to phamos users,
and brings everything over as Idea and Idea Writing Session:

- the stage countdown ∞ 9 7 5 3 1 Done becomes Seed … Harvest;
- an idea goes to the mapped user of its author, else to the default user;
- a session goes to the user of its idea (ideas and their sessions are private together);
- original creation and modification dates are kept, also on the first Version row;
- spawned_from is relinked once all ideas exist.

Every imported record remembers its source in `imported_from`, so a second run skips what is
already there. System Manager only.
"""

import requests

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_datetime, now_datetime

CHAPTER = "Implementation Chapter"
SESSION = "Writing Session"
CHAPTER_FIELDS = [
	"name",
	"owner",
	"creation",
	"modified",
	"title",
	"content",
	"writing_stage",
	"spawned_from",
	"last_session_words",
]
SESSION_FIELDS = [
	"name",
	"owner",
	"creation",
	"modified",
	"chapter",
	"user",
	"started_on",
	"ended_on",
	"duration_mins",
	"words_planned",
	"words_written",
	"aim_choice",
	"felt_productive",
]
STAGES = {
	"∞": "Seed",
	"9": "Sprout",
	"7": "Seedling",
	"5": "Young plant",
	"3": "Growing",
	"1": "Mature",
	"Done": "Harvest",
}
FEELINGS = {"productive": "Productive", "mixed": "Mixed", "not_really": "Not really"}
AIMS = ("more", "similar", "less")
PAGE = 500
TIMEOUT = 30


class NextChapterClient:
	"""Reads a NextChapter site with a username and password (a normal Frappe login)."""

	def __init__(self, url, username, password):
		self.url = (url or "").rstrip("/")
		self.username = username
		self.password = password
		self.session = requests.Session()

	def login(self):
		response = self.session.post(
			f"{self.url}/api/method/login",
			json={"usr": self.username, "pwd": self.password},
			timeout=TIMEOUT,
		)
		if response.status_code != 200:
			frappe.throw(_("Could not sign in to {0} (HTTP {1}).").format(self.url, response.status_code))

	def get_all(self, doctype, fields):
		rows, start = [], 0
		while True:
			response = self.session.get(
				f"{self.url}/api/resource/{doctype}",
				params={
					"fields": frappe.as_json(fields),
					"limit_start": start,
					"limit_page_length": PAGE,
					"order_by": "creation asc",
				},
				timeout=TIMEOUT,
			)
			if response.status_code != 200:
				frappe.throw(_("Could not read {0} from {1} (HTTP {2}).").format(doctype, self.url, response.status_code))
			batch = response.json().get("data") or []
			rows.extend(batch)
			if len(batch) < PAGE:
				return rows
			start += PAGE


def get_client(doc):
	"""Separate so tests can put a fake NextChapter in its place."""
	client = NextChapterClient(doc.source_url, doc.username, doc.get_password("password"))
	client.login()
	return client


class IdeaImport(Document):
	def validate(self):
		self.source_url = (self.source_url or "").strip().rstrip("/")
		if not self.source_url.startswith(("https://", "http://")):
			frappe.throw(_("The NextChapter site must start with https://"))

	def source_key(self, name):
		host = self.source_url.split("://", 1)[-1]
		return f"{host}/{name}"

	def user_for(self, remote_user):
		for row in self.users:
			if row.remote_user == remote_user and row.user:
				return row.user
		return None


def _get(name):
	"""The import record, for System Managers only (the doctype's only role)."""
	doc = frappe.get_doc("Idea Import", name)
	doc.check_permission("write")
	return doc


@frappe.whitelist(methods=["POST"])
def load_accounts(name):
	"""Fill the accounts table from the NextChapter site; keep mappings that are already set."""
	doc = _get(name)
	client = get_client(doc)
	chapters = client.get_all(CHAPTER, ["name", "owner"])
	sessions = client.get_all(SESSION, ["name", "chapter", "user"])
	counts = {}
	for row in chapters:
		counts.setdefault(row.get("owner"), [0, 0])[0] += 1
	owner_of = {row["name"]: row.get("owner") for row in chapters}
	for row in sessions:
		author = owner_of.get(row.get("chapter")) or row.get("user")
		counts.setdefault(author, [0, 0])[1] += 1

	kept = {row.remote_user: row.user for row in doc.users if row.user}
	doc.set("users", [])
	for remote_user, (ideas, sessions_count) in sorted(counts.items(), key=lambda item: -item[1][0]):
		if not remote_user:
			continue
		local = kept.get(remote_user) or (remote_user if frappe.db.exists("User", remote_user) else None)
		doc.append("users", {"remote_user": remote_user, "ideas": ideas, "sessions": sessions_count, "user": local})
	doc.status = "Accounts Loaded"
	doc.save()
	return {"accounts": len(doc.users)}


@frappe.whitelist(methods=["POST"])
def run_import(name):
	"""All or nothing: a failure undoes the partial import and keeps the error on the form."""
	doc = _get(name)
	client = get_client(doc)
	frappe.db.savepoint("idea_import")
	try:
		return import_from(doc, client)
	except Exception:
		frappe.db.rollback(save_point="idea_import")
		doc.reload()
		doc.status = "Failed"
		doc.log = frappe.get_traceback()
		doc.last_run_on = now_datetime()
		doc.save()
		frappe.msgprint(_("The import failed and was undone. The error is in the log."), indicator="red")
		return {"failed": True}


def _set_dates(doctype, name, creation, modified, owner=None):
	"""Original dates (and the owner, which Frappe overwrites on insert) after the insert."""
	values = {"owner": owner} if owner else {}
	if creation:
		values["creation"] = get_datetime(creation)
	if modified:
		values["modified"] = get_datetime(modified)
	if values:
		frappe.db.set_value(doctype, name, values, update_modified=False)


def import_from(doc, client):
	"""Bring chapters and sessions over. Returns the counts; the log goes on the form."""
	from phamos.api.personal_ideas import _snapshot

	log = []
	chapters = client.get_all(CHAPTER, CHAPTER_FIELDS)
	sessions = client.get_all(SESSION, SESSION_FIELDS)
	created = skipped = to_default = 0
	local_of = {}  # remote chapter name → local Idea name
	parent_of = {}  # remote chapter name → remote parent name

	for row in chapters:
		key = doc.source_key(row["name"])
		existing = frappe.db.get_value("Idea", {"imported_from": key}, "name")
		if existing:
			local_of[row["name"]] = existing
			skipped += 1
			continue
		user = doc.user_for(row.get("owner"))
		if not user:
			user = doc.default_user
			to_default += 1
			log.append(_("{0}: {1} has no match, given to {2}").format(row["name"], row.get("owner"), user))
		stage = STAGES.get(row.get("writing_stage") or "∞", "Seed")
		idea = frappe.get_doc(
			{
				"doctype": "Idea",
				"user": user,
				"title": row.get("title"),
				"content": row.get("content"),
				"stage": stage,
				"last_session_words": cint(row.get("last_session_words")),
				"imported_from": key,
			}
		)
		idea.flags.ignore_permissions = True
		idea.insert()
		_snapshot(idea, force=True)
		_set_dates("Idea", idea.name, row.get("creation"), row.get("modified"), owner=user)
		if row.get("creation"):
			frappe.db.set_value(
				"Version",
				{"ref_doctype": "Idea", "docname": idea.name},
				"creation",
				get_datetime(row["creation"]),
				update_modified=False,
			)
		if stage == "Harvest":
			frappe.db.set_value("Idea", idea.name, "harvested_on", get_datetime(row.get("modified")), update_modified=False)
		local_of[row["name"]] = idea.name
		if row.get("spawned_from"):
			parent_of[row["name"]] = row["spawned_from"]
		created += 1
		log.append(_("{0} → {1} ({2}, {3})").format(row["name"], idea.name, stage, user))

	# Side-idea links, once every idea exists. Only within one person's ideas (they are private).
	for remote, remote_parent in parent_of.items():
		child, parent = local_of.get(remote), local_of.get(remote_parent)
		if not (child and parent):
			continue
		if frappe.db.get_value("Idea", child, "user") != frappe.db.get_value("Idea", parent, "user"):
			log.append(_("{0}: came from {1}, but they belong to different people; link left out").format(child, parent))
			continue
		frappe.db.set_value("Idea", child, "spawned_from", parent, update_modified=False)

	sessions_created = 0
	for row in sessions:
		key = doc.source_key(row["name"])
		idea_name = local_of.get(row.get("chapter"))
		if not idea_name or frappe.db.exists("Idea Writing Session", {"imported_from": key}):
			continue
		started = row.get("started_on") or row.get("creation")
		felt = FEELINGS.get(row.get("felt_productive") or "")
		session = frappe.get_doc(
			{
				"doctype": "Idea Writing Session",
				"user": frappe.db.get_value("Idea", idea_name, "user"),
				"idea": idea_name,
				"started_on": get_datetime(started),
				"ended_on": get_datetime(row["ended_on"]) if row.get("ended_on") else None,
				"duration_mins": round(flt(row.get("duration_mins"))),
				"words_written": cint(row.get("words_written")),
				"word_goal": cint(row.get("words_planned")),
				"aim_choice": row.get("aim_choice") if row.get("aim_choice") in AIMS else None,
				"felt_productive": felt,
				"imported_from": key,
			}
		)
		session.insert(ignore_permissions=True)
		_set_dates("Idea Writing Session", session.name, row.get("creation"), row.get("modified"), owner=session.user)
		sessions_created += 1

	doc.reload()
	doc.status = "Imported"
	doc.ideas_created = created
	doc.sessions_created = sessions_created
	doc.skipped = skipped
	doc.to_default_user = to_default
	doc.last_run_on = now_datetime()
	doc.log = "\n".join(log) or _("Nothing new to import.")
	doc.save()
	return {
		"ideas_created": created,
		"sessions_created": sessions_created,
		"skipped": skipped,
		"to_default_user": to_default,
	}
