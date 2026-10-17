# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Issue chat: one Private Raven channel per Issue, opened from the cockpits (#1614, #1548).

Raven's own UI shows the chat; this module only links a channel to the record (Raven's
`linked_doctype` / `linked_document`), keeps its members in step with the record's owner and
assignees (add-only: nobody is removed when unassigned) and reports unread counts.

Reading the record is what grants the chat. Callers check that first (the cockpit wrappers in
`department_cockpit`, or `get_list` for the batched states), so the Raven records below are
written with `ignore_permissions`. Raven is a soft dependency: without it every state says
`enabled: False` and the hooks do nothing.
"""

from datetime import datetime
from urllib.parse import quote

import frappe
from frappe import _
from frappe.desk.form.load import get_assignments
from frappe.query_builder.functions import Count, Max
from frappe.utils import cint, escape_html, get_fullname, strip_html_tags

CHAT_DOCTYPES = ("Issue",)

# Department settings field → cockpit route. Raven's Issue links open the Issue in the first
# cockpit whose department matches, otherwise in the Personal Cockpit.
COCKPIT_PATHS = (
	("sales_department", "/sales-cockpit"),
	("human_resources_department", "/human-resources-cockpit"),
	("accounting_department", "/accounting-cockpit"),
	("project_management_department", "/project-management-cockpit"),
)
PERSONAL_COCKPIT_PATH = "/personal-cockpit"


def is_raven_installed():
	return "raven" in frappe.get_installed_apps()


def is_enabled():
	return is_raven_installed() and bool(
		cint(frappe.db.get_single_value("phamos Settings", "enable_issue_chat"))
	)


def _require_enabled():
	if not is_raven_installed():
		frappe.throw(_("Raven is not installed on this site."), title=_("Chat unavailable"))
	if not is_enabled():
		frappe.throw(_("Issue Chat is disabled in phamos Settings."), title=_("Chat unavailable"))


def _require_chat_doctype(doctype):
	if doctype not in CHAT_DOCTYPES:
		frappe.throw(_("Chats are not available for {0}.").format(_(doctype)))


# Raven v3 web routes (apps/web/src/App.tsx), encoded as Raven's own links encode them.
def channel_url(workspace, channel_id):
	return f"/raven/{quote(workspace, safe='')}/{quote(channel_id, safe='')}"


def dm_url(channel_id):
	return f"/raven/dm-channel/{quote(channel_id, safe='')}"


def find_channel(doctype, name):
	if not is_raven_installed():
		return None
	# An archived chat still belongs to its record (#1622): finding it keeps "Start chat" from
	# creating a second one for a closed Issue.
	return frappe.db.get_value(
		"Raven Channel",
		{
			"linked_doctype": doctype,
			"linked_document": name,
			"is_thread": 0,
			"is_direct_message": 0,
		},
		["name", "workspace", "is_archived"],
		as_dict=True,
		order_by="is_archived asc, creation asc",
	)


def _raven_user(user):
	if not user or user == "Guest":
		return None
	# Raven keeps the record but disables it when the user loses the "Raven User" role.
	return frappe.db.get_value("Raven User", {"user": user, "type": "User", "enabled": 1}, "name")


def _record_users(doc):
	users = [doc.owner] + [row.get("owner") for row in get_assignments(doc.doctype, doc.name)]
	return list(dict.fromkeys(u for u in users if u and u != "Guest"))


def _resolve_workspace():
	workspace = frappe.db.get_single_value("phamos Settings", "issue_chat_workspace")
	if workspace and frappe.db.exists("Raven Workspace", workspace):
		return workspace
	workspaces = frappe.get_all("Raven Workspace", pluck="name", order_by="creation asc", limit=1)
	if not workspaces:
		frappe.throw(_("No Raven Workspace found. Create one in Raven first."))
	return workspaces[0]


def _ensure_members(channel, users, admin=None, silent=False):
	"""Add the users to the channel and its workspace; return the users without a Raven user.

	`silent` skips Raven's "X added Y" line, for callers that post their own.
	"""
	existing = set(
		frappe.get_all("Raven Channel Member", filters={"channel_id": channel.name}, pluck="user_id")
	)
	skipped = []
	for user in users:
		raven_user = _raven_user(user)
		if not raven_user:
			skipped.append(user)
			continue
		# Raven only lists a workspace's channels to its members (#1308).
		if not frappe.db.exists(
			"Raven Workspace Member", {"user": raven_user, "workspace": channel.workspace}
		):
			frappe.get_doc(
				{"doctype": "Raven Workspace Member", "user": raven_user, "workspace": channel.workspace}
			).insert(ignore_permissions=True)
		if raven_user in existing:
			continue
		member = frappe.get_doc(
			{
				"doctype": "Raven Channel Member",
				"channel_id": channel.name,
				"user_id": raven_user,
				"is_admin": int(user == admin),
			}
		)
		member.flags.ignore_system_message = silent
		member.insert(ignore_permissions=True)
		existing.add(raven_user)
	return skipped


def _unread_counts(channel_ids):
	"""Unread messages per channel for the session user since their last visit, not counting their
	own (the intro message of a chat they just started would otherwise count)."""
	raven_user = _raven_user(frappe.session.user)
	if not raven_user or not channel_ids:
		return {}
	member = frappe.qb.DocType("Raven Channel Member")
	message = frappe.qb.DocType("Raven Message")
	rows = (
		frappe.qb.from_(member)
		.join(message)
		.on(message.channel_id == member.channel_id)
		.select(member.channel_id, Count(message.name).as_("unread"))
		.where(member.user_id == raven_user)
		.where(member.channel_id.isin(list(channel_ids)))
		.where(message.creation > member.last_visit)
		.where(message.message_type != "System")
		.where(message.owner != frappe.session.user)
		.groupby(member.channel_id)
	).run(as_dict=True)
	return {row.channel_id: row.unread for row in rows}


def _unread_thread_counts(channel_ids):
	"""Unread replies per chat in the threads of that chat the session user takes part in.

	Raven's own rule (raven.api.threads.get_unread_threads): per-thread last visit, no System
	messages, not counting the user's own. Raven shows these only on its Threads page, which the
	embedded chat hides, so the cockpit badges count them (#1623).
	"""
	return {channel: stats["unread"] for channel, stats in _unread_thread_stats(channel_ids).items()}


def _unread_thread_stats(channel_ids):
	"""Per chat: {"unread": replies, "last": newest unread reply} in its threads (see above)."""
	raven_user = _raven_user(frappe.session.user)
	if not raven_user or not channel_ids:
		return {}
	thread = frappe.qb.DocType("Raven Channel")
	root = frappe.qb.DocType("Raven Message")
	member = frappe.qb.DocType("Raven Channel Member")
	reply = frappe.qb.DocType("Raven Message", alias="reply")
	rows = (
		frappe.qb.from_(thread)
		# A thread channel is named after the message it hangs off, which sits in the chat.
		.join(root)
		.on(root.name == thread.name)
		.join(member)
		.on((member.channel_id == thread.name) & (member.user_id == raven_user))
		.join(reply)
		.on(reply.channel_id == thread.name)
		.select(root.channel_id, Count(reply.name).as_("unread"), Max(reply.creation).as_("last"))
		.where(thread.is_thread == 1)
		.where(root.channel_id.isin(list(channel_ids)))
		.where(reply.creation > member.last_visit)
		.where(reply.message_type != "System")
		.where(reply.owner != frappe.session.user)
		.groupby(root.channel_id)
	).run(as_dict=True)
	return {row.channel_id: {"unread": row.unread, "last": row.last} for row in rows}


def _unread_threads(channel_id, limit=50):
	"""The threads of one chat with unread replies for the session user, newest reply first:
	[{thread_id, unread, preview, last_sender}] for the hint above the chat and the marks on the
	thread pills (#1623)."""
	raven_user = _raven_user(frappe.session.user)
	if not raven_user:
		return []
	thread = frappe.qb.DocType("Raven Channel")
	root = frappe.qb.DocType("Raven Message")
	member = frappe.qb.DocType("Raven Channel Member")
	reply = frappe.qb.DocType("Raven Message", alias="reply")
	rows = (
		frappe.qb.from_(thread)
		.join(root)
		.on(root.name == thread.name)
		.join(member)
		.on((member.channel_id == thread.name) & (member.user_id == raven_user))
		.join(reply)
		.on(reply.channel_id == thread.name)
		.select(
			thread.name.as_("thread_id"),
			root.text.as_("root_text"),
			Count(reply.name).as_("unread"),
			Max(reply.creation).as_("last_reply"),
		)
		.where(thread.is_thread == 1)
		.where(root.channel_id == channel_id)
		.where(reply.creation > member.last_visit)
		.where(reply.message_type != "System")
		.where(reply.owner != frappe.session.user)
		.groupby(thread.name, root.text)
		.orderby(Max(reply.creation), order=frappe.qb.desc)
		.limit(limit)
	).run(as_dict=True)
	result = []
	for row in rows:
		last_owner = frappe.db.get_value(
			"Raven Message",
			{"channel_id": row.thread_id, "creation": row.last_reply},
			"owner",
		)
		preview = strip_html_tags(row.root_text or "").strip()
		result.append(
			{
				"thread_id": row.thread_id,
				"unread": row.unread,
				"preview": (preview[:80] + "…") if len(preview) > 80 else preview,
				"last_sender": _display_name(last_owner) if last_owner else "",
			}
		)
	return result


def _first_unread_message(channel_id):
	"""The oldest message in a chat the session user has not read yet, or None: where the chat
	opens when it is opened from a list (#1617)."""
	raven_user = _raven_user(frappe.session.user)
	last_visit = raven_user and frappe.db.get_value(
		"Raven Channel Member", {"channel_id": channel_id, "user_id": raven_user}, "last_visit"
	)
	if not last_visit:
		return None
	rows = frappe.get_all(
		"Raven Message",
		filters={
			"channel_id": channel_id,
			"creation": (">", last_visit),
			"message_type": ("!=", "System"),
			"owner": ("!=", frappe.session.user),
		},
		pluck="name",
		order_by="creation asc",
		limit=1,
	)
	return rows[0] if rows else None


def _member_channels(channel_ids):
	raven_user = _raven_user(frappe.session.user)
	if not raven_user or not channel_ids:
		return set()
	return set(
		frappe.get_all(
			"Raven Channel Member",
			filters={"channel_id": ("in", list(channel_ids)), "user_id": raven_user},
			pluck="channel_id",
		)
	)


def get_chat(doc):
	"""Chat state of a record the caller may read (no chat yet: `channel_id` is None)."""
	_require_chat_doctype(doc.doctype)
	state = {
		"enabled": is_enabled(),
		"channel_id": None,
		"workspace": None,
		"url": None,
		"is_member": False,
		"archived": False,
		"unread": 0,
		"unread_threads": 0,
		"threads": [],
		"skipped_users": [],
	}
	if not state["enabled"]:
		return state

	state["skipped_users"] = [
		{"user": user, "full_name": get_fullname(user)}
		for user in _record_users(doc)
		if not _raven_user(user)
	]
	channel = find_channel(doc.doctype, doc.name)
	if not channel:
		return state

	state.update(
		channel_id=channel.name,
		workspace=channel.workspace,
		url=channel_url(channel.workspace, channel.name),
		archived=bool(channel.is_archived),
		is_member=channel.name in _member_channels([channel.name]),
		unread=_unread_counts([channel.name]).get(channel.name, 0),
		unread_threads=_unread_thread_counts([channel.name]).get(channel.name, 0),
	)
	if state["unread_threads"]:
		state["threads"] = _unread_threads(channel.name)
	return state


def ensure_chat(doc):
	"""Get or create the record's chat and make the session user, owner and assignees members.

	"Start chat" and "Join chat" both end here, so it is safe to call again.
	"""
	_require_chat_doctype(doc.doctype)
	_require_enabled()
	if not _raven_user(frappe.session.user):
		frappe.throw(_("You need to be a Raven user to chat."))

	channel = find_channel(doc.doctype, doc.name)
	created = False
	if not channel:
		channel = _create_channel(doc)
		created = True

	users = [frappe.session.user] + _record_users(doc)
	_ensure_members(channel, users, admin=frappe.session.user if created else None)
	if created:
		_post_link_message(
			channel.name,
			doc,
			_("Chat about {0}: {1}").format(doc.name, _doc_title(doc)),
		)
	return get_chat(doc)


def _create_channel(doc):
	workspace = _resolve_workspace()
	channel = frappe.get_doc(
		{
			"doctype": "Raven Channel",
			"channel_name": f"{doc.doctype}-{doc.name}",
			"channel_description": f"{doc.name}: {_doc_title(doc)}"[:140],
			"type": "Private",
			"workspace": workspace,
			"linked_doctype": doc.doctype,
			"linked_document": doc.name,
		}
	)
	# Members are added by _ensure_members, with the creator as admin.
	channel.flags.do_not_add_member = True
	try:
		channel.insert(ignore_permissions=True)
	except (frappe.DuplicateEntryError, frappe.ValidationError):
		# Someone else created it a moment ago.
		existing = find_channel(doc.doctype, doc.name)
		if not existing:
			raise
		return existing
	return frappe._dict(name=channel.name, workspace=channel.workspace)


def _doc_title(doc):
	return doc.get("subject") or doc.name


def _post_link_message(channel_id, doc, text):
	"""Post a Raven document-link message (Raven renders it as a card for the record)."""
	frappe.get_doc(
		{
			"doctype": "Raven Message",
			"channel_id": channel_id,
			"message_type": "Text",
			"text": f"<p>{escape_html(text)}</p>",
			"link_doctype": doc.doctype,
			"link_document": doc.name,
		}
	).insert(ignore_permissions=True)


def get_chat_states(doctype, names):
	"""Batched chat state for list views: {name: {channel_id, is_member, archived, unread,
	unread_threads, first_unread, first_unread_thread}}.

	Only records the session user may read and that have a chat are returned.
	"""
	_require_chat_doctype(doctype)
	names = frappe.parse_json(names) if isinstance(names, str) else names
	if not is_enabled() or not names:
		return {}
	readable = frappe.get_list(
		doctype, filters={"name": ("in", list(names))}, pluck="name", limit_page_length=0
	)
	if not readable:
		return {}
	channels = frappe.get_all(
		"Raven Channel",
		filters={
			"linked_doctype": doctype,
			"linked_document": ("in", readable),
			"is_thread": 0,
			"is_direct_message": 0,
		},
		fields=["name", "linked_document", "is_archived"],
		order_by="is_archived desc",  # a live chat wins over an archived one below
	)
	channel_ids = [c.name for c in channels]
	members = _member_channels(channel_ids)
	unread = _unread_counts(channel_ids)
	unread_threads = _unread_thread_counts(channel_ids)
	states = {}
	for c in channels:
		state = {
			"channel_id": c.name,
			"is_member": c.name in members,
			"archived": bool(c.is_archived),
			"unread": unread.get(c.name, 0),
			"unread_threads": unread_threads.get(c.name, 0),
			# Where the chat opens from the list: the first new message, else the thread with
			# the newest unread reply (#1617).
			"first_unread": None,
			"first_unread_thread": None,
		}
		if state["unread"]:
			state["first_unread"] = _first_unread_message(c.name)
		elif state["unread_threads"]:
			threads = _unread_threads(c.name, limit=1)
			state["first_unread_thread"] = threads[0]["thread_id"] if threads else None
		states[c.linked_document] = state
	return states


def get_unread_chats(doctype="Issue", limit=5):
	"""The record chats the session user is in with unread messages or thread replies, newest
	activity first (#1618): {"total": n, "chats": [{name, subject, unread, unread_threads,
	last_sender, last_activity, first_unread, first_unread_thread}], "channel_ids": [...]}.

	Only records the user may read; archived chats (closed Issues) are left out. Counting and
	ordering take a few queries for all chats; the details (who wrote, where to land) are only
	looked up for the `limit` chats that are shown. `channel_ids` lists all the user's chats of
	this doctype, so the page can tell which of Raven's realtime events concern it.
	"""
	_require_chat_doctype(doctype)
	limit = max(1, cint(limit) or 5)
	empty = {"total": 0, "chats": [], "channel_ids": []}
	raven_user = _raven_user(frappe.session.user)
	if not is_enabled() or not raven_user:
		return empty
	member_of = frappe.get_all(
		"Raven Channel Member", filters={"user_id": raven_user}, pluck="channel_id", limit_page_length=0
	)
	if not member_of:
		return empty
	channels = frappe.get_all(
		"Raven Channel",
		filters={
			"name": ("in", member_of),
			"linked_doctype": doctype,
			"is_archived": 0,
			"is_thread": 0,
			"is_direct_message": 0,
		},
		fields=["name", "linked_document", "last_message_timestamp"],
		limit_page_length=0,
	)
	if not channels:
		return empty
	ids = [c.name for c in channels]
	unread = _unread_counts(ids)
	thread_stats = _unread_thread_stats(ids)
	pending = [c for c in channels if unread.get(c.name) or c.name in thread_stats]
	if pending:
		readable = set(
			frappe.get_list(
				doctype,
				filters={"name": ("in", [c.linked_document for c in pending])},
				pluck="name",
				limit_page_length=0,
			)
		)
		pending = [c for c in pending if c.linked_document in readable]

	def activity(channel):
		# Newest of: the chat's last message (when something in it is unread) and the newest
		# unread thread reply.
		times = [thread_stats.get(channel.name, {}).get("last")]
		if unread.get(channel.name):
			times.append(channel.last_message_timestamp)
		return max((t for t in times if t), default=None)

	pending.sort(key=lambda c: activity(c) or datetime.min, reverse=True)
	shown = pending[:limit]

	title_field = "subject" if frappe.get_meta(doctype).has_field("subject") else "name"
	titles = (
		dict(
			frappe.get_all(
				doctype,
				filters={"name": ("in", [c.linked_document for c in shown])},
				fields=["name", title_field],
				as_list=True,
			)
		)
		if shown
		else {}
	)
	chats = [_unread_chat_details(c, titles, unread, thread_stats, activity(c)) for c in shown]
	return {"total": len(pending), "chats": chats, "channel_ids": ids}


def _unread_chat_details(channel, titles, unread, thread_stats, last_activity):
	chat = {
		"name": channel.linked_document,
		"subject": titles.get(channel.linked_document) or channel.linked_document,
		"unread": unread.get(channel.name, 0),
		"unread_threads": thread_stats.get(channel.name, {}).get("unread", 0),
		"last_sender": "",
		"last_activity": last_activity,
		"first_unread": None,
		"first_unread_thread": None,
	}
	if chat["unread"]:
		chat["first_unread"] = _first_unread_message(channel.name)
		last = frappe.get_all(
			"Raven Message",
			filters={
				"channel_id": channel.name,
				"message_type": ("!=", "System"),
				"owner": ("!=", frappe.session.user),
			},
			fields=["owner", "creation"],
			order_by="creation desc",
			limit=1,
		)
		if last:
			chat["last_sender"] = _display_name(last[0].owner)
	threads = _unread_threads(channel.name, limit=1) if chat["unread_threads"] else []
	if threads:
		if not chat["first_unread"]:
			chat["first_unread_thread"] = threads[0]["thread_id"]
		thread_last = thread_stats[channel.name]["last"]
		if not chat["last_sender"] or (last_activity and thread_last == last_activity):
			chat["last_sender"] = threads[0]["last_sender"] or chat["last_sender"]
	return chat


def start_dm(doc, user):
	"""Open the Raven DM with `user`, post a link to the record, and return its URL.

	The link is posted only when `user` may read the record (`linked` says whether it was) and
	the DM's last message is not already a link to it, so clicking "Message" twice does not
	repeat it.
	"""
	_require_chat_doctype(doc.doctype)
	_require_enabled()
	from raven.api.raven_channel import create_direct_message_channel

	channel_id = create_direct_message_channel(user)
	# The link and the record's title only go to someone who may open the record; for anyone
	# else the DM opens as it is (review of #1616).
	if not frappe.has_permission(doc.doctype, "read", doc=doc.name, user=user):
		return {"channel_id": channel_id, "url": dm_url(channel_id), "linked": False}
	last = frappe.get_all(
		"Raven Message",
		filters={"channel_id": channel_id, "message_type": ("!=", "System")},
		fields=["link_doctype", "link_document"],
		order_by="creation desc",
		limit=1,
	)
	if not last or (last[0].link_doctype, last[0].link_document) != (doc.doctype, doc.name):
		_post_link_message(channel_id, doc, _("About {0}: {1}").format(doc.name, _doc_title(doc)))
	return {"channel_id": channel_id, "url": dm_url(channel_id), "linked": True}


# --- Hooks -----------------------------------------------------------------------------------


def sync_assignee(doc, method=None):
	"""ToDo on_update: assignments of a record with a chat show up in it (#1614, #1621).

	A new assignee joins the chat, with one "assigned" line instead of Raven's "added" one.
	Unassigning posts a line and keeps them in the chat. Closing a ToDo (the work is done, or
	the record was closed) posts nothing. Never blocks the assignment when Raven fails.
	"""
	if doc.reference_type not in CHAT_DOCTYPES or not doc.allocated_to:
		return
	before = doc.get_doc_before_save()
	was_open = bool(before and before.status == "Open" and before.allocated_to == doc.allocated_to)
	assigned = doc.status == "Open" and not was_open
	unassigned = doc.status == "Cancelled" and was_open
	if not (assigned or unassigned) or not is_enabled():
		return
	channel = find_channel(doc.reference_type, doc.reference_name)
	if not channel:
		return
	actor, person = _display_name(frappe.session.user), _display_name(doc.allocated_to)
	try:
		if assigned:
			_ensure_members(channel, [doc.allocated_to], silent=True)
			_post_system_message(channel.name, _("{0} assigned {1}.").format(actor, person))
		else:
			_post_system_message(channel.name, _("{0} unassigned {1}.").format(actor, person))
	except Exception:
		frappe.log_error(title=f"Issue chat: could not post the assignment of {doc.allocated_to}")


def on_issue_update(doc, method=None):
	"""Issue on_update: status changes show up in its chat; Closed archives it, reopening brings
	it back (#1621, #1622). Never blocks the save when Raven fails."""
	before = doc.get_doc_before_save()
	if not before or before.status == doc.status or not is_enabled():
		return
	channel = find_channel(doc.doctype, doc.name)
	if not channel:
		return
	try:
		if before.status == "Closed" and channel.is_archived:
			_set_archived(channel.name, False)
		_post_system_message(
			channel.name,
			_("{0} set the status to {1}.").format(_display_name(frappe.session.user), _(doc.status)),
		)
		if doc.status == "Closed" and not channel.is_archived:
			_set_archived(channel.name, True)
	except Exception:
		frappe.log_error(title=f"Issue chat: could not follow the status of {doc.name}")


def on_task_insert(doc, method=None):
	"""Task after_insert: an Issue converted to this Task says so in its chat (#1621)."""
	issue = doc.get("issue")
	if not issue or not is_enabled():
		return
	channel = find_channel("Issue", issue)
	if not channel or channel.is_archived:
		return
	try:
		_post_system_message(
			channel.name,
			_("{0} converted this Issue to Task {1}.").format(_display_name(frappe.session.user), doc.name),
		)
	except Exception:
		frappe.log_error(title=f"Issue chat: could not post the conversion of {issue}")


def _display_name(user):
	"""The name Raven shows for the user, so our lines match Raven's own."""
	return frappe.db.get_value("Raven User", {"user": user}, "full_name") or get_fullname(user)


def _post_system_message(channel_id, text):
	"""A grey Raven System line: shown to everyone, counted as unread by nobody."""
	frappe.get_doc(
		{"doctype": "Raven Message", "channel_id": channel_id, "message_type": "System", "text": text}
	).insert(ignore_permissions=True)


def _set_archived(channel_id, archived):
	"""Archive or restore a chat. Raven's own save only lets channel admins do this, while the
	record's status is what decides here, so the flag is written directly."""
	frappe.db.set_value("Raven Channel", channel_id, "is_archived", int(archived))
	frappe.clear_document_cache("Raven Channel", channel_id)
	from raven.utils import get_raven_room

	frappe.publish_realtime(
		"channel_list_updated", {"channel_id": channel_id}, room=get_raven_room(), after_commit=True
	)


def add_mentioned_members(doc, method=None):
	"""Raven Message validate: people mentioned in an Issue chat (or one of its threads) join it.

	Runs after Raven has read the mentions from the HTML and before the insert, so Raven's own
	after_insert already treats them as members: it notifies them and adds them to the thread
	(it only adds people who are in the parent channel). Only people who can read the record
	are added; for anyone else Raven's "isn't in this channel" warning stays (#1620).
	"""
	if not doc.get("mentions") or doc.message_type == "System" or not is_enabled():
		return
	channel = _chat_channel_of(doc.channel_id)
	if not channel:
		return
	members = set(
		frappe.get_all("Raven Channel Member", filters={"channel_id": channel.name}, pluck="user_id")
	)
	users = []
	for raven_user in dict.fromkeys(m.user for m in doc.mentions if m.user):
		if raven_user in members:
			continue
		user = frappe.db.get_value("Raven User", {"name": raven_user, "type": "User", "enabled": 1}, "user")
		if user and frappe.has_permission(
			channel.linked_doctype, "read", doc=channel.linked_document, user=user
		):
			users.append(user)
	if not users:
		return
	try:
		_ensure_members(channel, users)
	except Exception:
		frappe.log_error(title=f"Issue chat: could not add mentioned users to {channel.name}")


def _chat_channel_of(channel_id):
	"""The record chat a channel belongs to: itself, or the parent channel of a thread."""
	fields = ["name", "workspace", "linked_doctype", "linked_document", "is_thread", "is_direct_message"]
	channel = frappe.db.get_value("Raven Channel", channel_id, fields, as_dict=True)
	if channel and channel.is_thread:
		# A thread channel is named after the message it hangs off.
		parent_id = frappe.db.get_value("Raven Message", channel_id, "channel_id")
		channel = frappe.db.get_value("Raven Channel", parent_id, fields, as_dict=True) if parent_id else None
	if not channel or channel.is_direct_message or channel.linked_doctype not in CHAT_DOCTYPES:
		return None
	return channel


def document_link(doctype, docname):
	"""raven_document_link_override: Raven opens Issue links in the matching cockpit."""
	if doctype != "Issue":
		return None
	return f"{issue_cockpit_path(docname)}/issues/list/{docname}"


def issue_cockpit_path(name):
	fields = ["project"]
	if frappe.get_meta("Issue").has_field("custom_department"):
		fields.append("custom_department")
	issue = frappe.db.get_value("Issue", name, fields, as_dict=True) or frappe._dict()
	department = issue.get("custom_department")
	if not department and issue.project:
		department = frappe.db.get_value("Project", issue.project, "department")
	if department:
		settings_meta = frappe.get_meta("phamos Settings")
		for fieldname, path in COCKPIT_PATHS:
			if settings_meta.has_field(fieldname) and (
				frappe.db.get_single_value("phamos Settings", fieldname) == department
			):
				return path
	return PERSONAL_COCKPIT_PATH
