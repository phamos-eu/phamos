# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Issue / Checklist ↔ Raven chat helpers for I Own My Work SPA."""

import re

import frappe
from frappe import _
from frappe.desk.form.load import get_assignments
from frappe.utils import cint, get_fullname, get_url

LINKED_CHAT_DOCTYPES = ("Issue", "Checklist", "Task")


def _parse_list(value):
	import json

	if value is None or value == "":
		return []
	if isinstance(value, list):
		return value
	if isinstance(value, str):
		try:
			parsed = json.loads(value)
			return parsed if isinstance(parsed, list) else [value]
		except (TypeError, ValueError):
			return [u.strip() for u in value.split(",") if u.strip()]
	return []


def is_raven_installed():
	return "raven" in frappe.get_installed_apps()


def get_chat_feature_flags():
	"""Soft-dependency flags for the SPA."""
	installed = is_raven_installed()
	enabled = False
	workspace = None
	if installed:
		try:
			settings = frappe.get_cached_doc("phamos Settings")
			enabled = bool(cint(settings.get("enable_issue_raven_chat")))
			workspace = settings.get("issue_raven_workspace")
		except Exception:
			enabled = False
	return {
		"raven_installed": installed,
		"enabled": enabled and installed,
		"workspace": workspace,
		"raven_unavailable": not installed,
	}


def _require_raven_feature():
	flags = get_chat_feature_flags()
	if not flags["raven_installed"]:
		frappe.throw(_("Raven is not installed on this site"), title=_("Raven unavailable"))
	if not flags["enabled"]:
		frappe.throw(
			_("Issue Raven Chat is disabled in phamos Settings"),
			title=_("Feature disabled"),
		)
	return flags


def _require_issue_read(name):
	return _require_linked_read("Issue", name)


def _require_issue_write(name):
	return _require_linked_write("Issue", name)


def _require_linked_read(doctype, name):
	if doctype not in LINKED_CHAT_DOCTYPES:
		frappe.throw(_("Unsupported linked doctype: {0}").format(doctype))
	frappe.has_permission(doctype, "read", throw=True)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return doc


def _require_linked_write(doctype, name):
	if doctype not in LINKED_CHAT_DOCTYPES:
		frappe.throw(_("Unsupported linked doctype: {0}").format(doctype))
	frappe.has_permission(doctype, "write", throw=True)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("write")
	return doc


def find_linked_channel(doctype, docname):
	if not is_raven_installed() or doctype not in LINKED_CHAT_DOCTYPES:
		return None
	return frappe.db.get_value(
		"Raven Channel",
		{"linked_doctype": doctype, "linked_document": docname, "is_archived": 0},
		"name",
	)


def find_issue_channel(issue_name):
	return find_linked_channel("Issue", issue_name)


def _resolve_workspace():
	flags = get_chat_feature_flags()
	workspace = flags.get("workspace")
	if workspace and frappe.db.exists("Raven Workspace", workspace):
		return workspace
	# Prefer non-archived workspaces if the field exists
	workspaces = frappe.get_all("Raven Workspace", pluck="name", limit_page_length=1, order_by="creation asc")
	if not workspaces:
		frappe.throw(_("No Raven Workspace found. Create one in Raven first."))
	return workspaces[0]


def _user_to_raven_user(user):
	"""Map Frappe User → Raven User name (member user_id)."""
	if not user or user in ("Guest", "Administrator"):
		# Administrator may still have a Raven User row
		pass
	if frappe.db.exists("Raven User", user):
		return user
	name = frappe.db.get_value("Raven User", {"user": user, "type": "User"}, "name")
	return name


def _channel_member_raven_users(channel_id):
	return set(
		frappe.get_all(
			"Raven Channel Member",
			filters={"channel_id": channel_id},
			pluck="user_id",
		)
	)


def _add_members(channel_id, raven_users, *, keep_extras=True):
	"""Ensure raven_users are members. Does not remove extras when keep_extras=True."""
	existing = _channel_member_raven_users(channel_id)
	for raven_user in raven_users:
		if not raven_user or raven_user in existing:
			continue
		try:
			doc = frappe.get_doc(
				{
					"doctype": "Raven Channel Member",
					"channel_id": channel_id,
					"user_id": raven_user,
				}
			)
			doc.insert(ignore_permissions=False)
			existing.add(raven_user)
		except frappe.DuplicateEntryError:
			pass
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Failed to add Raven member {raven_user} to {channel_id}",
			)


def _channel_name_for_linked(doctype, doc):
	# autoname: "{workspace}-{channel_name}" with spaces → hyphens
	prefix_map = {"Issue": "issue", "Checklist": "checklist", "Task": "task"}
	prefix = prefix_map.get(doctype, doctype.lower())
	safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", doc.name).strip("-").lower()
	return f"{prefix}-{safe}"


def _channel_name_for_issue(issue_doc):
	return _channel_name_for_linked("Issue", issue_doc)


def _member_users_for_doc(doctype, doc):
	users = {doc.owner}
	if doctype in ("Issue", "Task"):
		for row in get_assignments(doctype, doc.name):
			if row.get("owner"):
				users.add(row["owner"])
	users.discard(None)
	users.discard("")
	return users


def _issue_member_users(issue_doc):
	return _member_users_for_doc("Issue", issue_doc)


def _spa_path_for(doctype, name):
	if doctype == "Checklist":
		return f"/i-own-my-work/checklists/{name}"
	if doctype == "Task":
		department = frappe.db.get_value("Task", name, "department")
		sales_department = frappe.db.get_single_value("phamos Settings", "sales_department")
		hr_department = frappe.db.get_single_value("phamos Settings", "hr_department")
		accounting_department = frappe.db.get_single_value("phamos Settings", "accounting_department")
		pm_department = frappe.db.get_single_value("phamos Settings", "pm_department")
		if department and sales_department and department == sales_department:
			return f"/sales-cockpit/tasks/{name}"
		if department and hr_department and department == hr_department:
			return f"/hr-cockpit/tasks/{name}"
		if department and accounting_department and department == accounting_department:
			return f"/accounting-cockpit/tasks/{name}"
		if department and pm_department and department == pm_department:
			return f"/project-management-cockpit/tasks/{name}"
		return f"/hr-cockpit/tasks/{name}"
	return f"/i-own-my-work/issues/{name}"


def _doc_label(doctype, doc):
	if doctype in ("Issue", "Task"):
		return doc.subject or doc.name
	return doc.name


def sync_linked_channel_members(doctype, name, *, force=False):
	"""Add owner (+ Issue assignees) as Raven Channel Members. Keeps invited extras."""
	if not is_raven_installed() or doctype not in LINKED_CHAT_DOCTYPES:
		return None

	channel_id = find_linked_channel(doctype, name)
	if not channel_id:
		return None

	if not force:
		flags = get_chat_feature_flags()
		if not flags["enabled"]:
			return channel_id

	doc = frappe.get_doc(doctype, name)
	desired_users = _member_users_for_doc(doctype, doc)
	raven_users = []
	for user in desired_users:
		ru = _user_to_raven_user(user)
		if ru:
			raven_users.append(ru)

	_add_members(channel_id, raven_users, keep_extras=True)
	return channel_id


def sync_issue_channel_members(name, *, force=False):
	return sync_linked_channel_members("Issue", name, force=force)


def _reply_preview(details):
	"""Short preview text from replied_message_details (dict or JSON string)."""
	if not details:
		return ""
	if isinstance(details, str):
		import json

		try:
			details = json.loads(details)
		except (TypeError, ValueError):
			return (details or "")[:120]
	if not isinstance(details, dict):
		return ""
	text = details.get("text") or details.get("content") or ""
	# Strip simple HTML tags for preview
	text = re.sub(r"<[^>]+>", "", str(text)).strip()
	owner = details.get("owner")
	owner_label = get_fullname(owner) if owner else ""
	preview = text[:120] + ("…" if len(text) > 120 else "")
	if owner_label and preview:
		return f"{owner_label}: {preview}"
	return preview or owner_label


def _serialize_one_message(m):
	owner = m.get("owner")
	return {
		"name": m.get("name"),
		"owner": owner,
		"owner_name": get_fullname(owner) if owner else "",
		"creation": m.get("creation"),
		"text": m.get("text") or m.get("content") or "",
		"message_type": m.get("message_type"),
		"is_bot_message": m.get("is_bot_message"),
		"is_thread": cint(m.get("is_thread")),
		"is_reply": cint(m.get("is_reply")),
		"linked_message": m.get("linked_message"),
		"reply_preview": _reply_preview(m.get("replied_message_details")),
	}


def _serialize_messages(messages):
	out = [_serialize_one_message(m) for m in (messages or [])]
	# SPA expects chronological ascending
	out.reverse()
	return out


def _assert_linked_channel_access(channel_id, linked_doctype=None, linked_document=None):
	"""
	Allow access when channel (or thread parent) is linked to Issue or Checklist.
	Returns (doctype, docname).
	"""
	if not channel_id:
		frappe.throw(_("channel_id is required"))

	channel = frappe.db.get_value(
		"Raven Channel",
		channel_id,
		["name", "linked_doctype", "linked_document", "is_thread"],
		as_dict=True,
	)
	if not channel:
		frappe.throw(_("Channel not found"))

	def _check(doctype, docname):
		if doctype not in LINKED_CHAT_DOCTYPES or not docname:
			return None
		if linked_doctype and doctype != linked_doctype:
			frappe.throw(_("Channel does not belong to this document"))
		if linked_document and docname != linked_document:
			frappe.throw(_("Channel does not belong to this document"))
		_require_linked_read(doctype, docname)
		return doctype, docname

	hit = _check(channel.linked_doctype, channel.linked_document)
	if hit:
		return hit

	if cint(channel.is_thread):
		root = frappe.db.get_value(
			"Raven Message",
			channel_id,
			["name", "channel_id"],
			as_dict=True,
		)
		if not root or not root.channel_id:
			frappe.throw(_("Thread root message not found"))
		parent = frappe.db.get_value(
			"Raven Channel",
			root.channel_id,
			["linked_doctype", "linked_document"],
			as_dict=True,
		)
		if parent:
			hit = _check(parent.linked_doctype, parent.linked_document)
			if hit:
				return hit

	frappe.throw(_("Not an I Own My Work discussion channel"))


def _assert_issue_channel_access(channel_id, issue_name=None):
	_doctype, docname = _assert_linked_channel_access(
		channel_id, linked_doctype="Issue" if issue_name else None, linked_document=issue_name
	)
	return docname


def _resolve_linked_args(linked_doctype=None, linked_document=None, issue_name=None):
	"""Normalize SPA args; issue_name remains supported for Issue chat."""
	if issue_name and not linked_document:
		linked_doctype = linked_doctype or "Issue"
		linked_document = issue_name
	linked_doctype = linked_doctype or "Issue"
	if linked_doctype not in LINKED_CHAT_DOCTYPES:
		frappe.throw(_("Unsupported linked doctype: {0}").format(linked_doctype))
	if not linked_document:
		frappe.throw(_("Document name is required"))
	return linked_doctype, linked_document


def _serialize_members(channel_id):
	rows = frappe.get_all(
		"Raven Channel Member",
		filters={"channel_id": channel_id},
		fields=["user_id", "is_admin"],
	)
	result = []
	for r in rows:
		user = frappe.db.get_value("Raven User", r.user_id, "user") or r.user_id
		result.append(
			{
				"raven_user": r.user_id,
				"user": user,
				"full_name": get_fullname(user) if user else r.user_id,
				"is_admin": r.is_admin,
			}
		)
	return result


@frappe.whitelist()
def get_document_chat(linked_doctype, name, limit=50):
	"""Resolve linked channel + recent messages for Issue or Checklist."""
	linked_doctype, name = _resolve_linked_args(linked_doctype, name)
	_require_linked_read(linked_doctype, name)
	flags = get_chat_feature_flags()
	if not flags["enabled"]:
		return {
			"channel_id": None,
			"members": [],
			"messages": [],
			**flags,
		}

	channel_id = find_linked_channel(linked_doctype, name)
	if not channel_id:
		return {"channel_id": None, "members": [], "messages": [], **flags}

	doc = frappe.get_doc(linked_doctype, name)
	ru = _user_to_raven_user(frappe.session.user)
	if ru and ru not in _channel_member_raven_users(channel_id):
		if (
			frappe.session.user in _member_users_for_doc(linked_doctype, doc)
			or frappe.session.user == "Administrator"
		):
			_add_members(channel_id, [ru])

	payload = _fetch_messages(channel_id, limit=cint(limit) or 50)
	return {
		"channel_id": channel_id,
		"members": _serialize_members(channel_id),
		"messages": _serialize_messages(payload.get("messages")),
		"has_old_messages": payload.get("has_old_messages"),
		"raven_url": f"/raven/channel/{channel_id}",
		**flags,
	}


@frappe.whitelist()
def get_issue_chat(name, limit=50):
	return get_document_chat("Issue", name, limit=limit)


@frappe.whitelist()
def ensure_document_channel(linked_doctype, name):
	"""Get-or-create a Private Raven Channel linked to Issue or Checklist."""
	_require_raven_feature()
	linked_doctype, name = _resolve_linked_args(linked_doctype, name)
	doc = _require_linked_write(linked_doctype, name)

	existing = find_linked_channel(linked_doctype, name)
	if existing:
		sync_linked_channel_members(linked_doctype, name)
		return get_document_chat(linked_doctype, name)

	workspace = _resolve_workspace()
	label = _doc_label(linked_doctype, doc)
	channel = frappe.get_doc(
		{
			"doctype": "Raven Channel",
			"channel_name": _channel_name_for_linked(linked_doctype, doc),
			"channel_description": f"{doc.name}: {label}",
			"type": "Private",
			"workspace": workspace,
			"linked_doctype": linked_doctype,
			"linked_document": doc.name,
			"is_synced": 1,
		}
	)
	channel.insert()
	channel_id = channel.name

	if frappe.db.get_value("Raven Channel", channel_id, "linked_document") != doc.name:
		frappe.db.set_value(
			"Raven Channel",
			channel_id,
			{
				"linked_doctype": linked_doctype,
				"linked_document": doc.name,
				"is_synced": 1,
			},
			update_modified=False,
		)

	sync_linked_channel_members(linked_doctype, name, force=True)

	ru = _user_to_raven_user(frappe.session.user)
	if ru:
		_add_members(channel_id, [ru])

	spa_url = get_url(_spa_path_for(linked_doctype, doc.name))
	intro = (
		f"Discussion started for **{doc.name}**: {label}\n\n"
		f"[Open in I Own My Work]({spa_url})"
	)
	frappe.get_doc(
		{
			"doctype": "Raven Message",
			"channel_id": channel_id,
			"message_type": "Text",
			"text": intro,
			"json": {
				"type": "doc",
				"content": [
					{
						"type": "paragraph",
						"content": [{"type": "text", "text": intro}],
					}
				],
			},
			"link_doctype": linked_doctype,
			"link_document": doc.name,
		}
	).insert()

	return get_document_chat(linked_doctype, name)


@frappe.whitelist()
def ensure_issue_channel(name):
	return ensure_document_channel("Issue", name)


def _fetch_messages(channel_id, limit=50, before=None):
	if before:
		from raven.api.chat_stream import get_older_messages

		return get_older_messages(channel_id=channel_id, from_message=before, limit=limit)
	from raven.api.chat_stream import get_messages

	return get_messages(channel_id=channel_id, limit=limit)


@frappe.whitelist()
def get_chat_messages(
	channel_id, limit=50, before=None, issue_name=None, linked_doctype=None, linked_document=None
):
	"""Fetch messages for a channel the user can access."""
	_require_raven_feature()
	if not channel_id:
		frappe.throw(_("channel_id is required"))

	doctype, docname = _resolve_linked_args(linked_doctype, linked_document, issue_name)
	_assert_linked_channel_access(channel_id, linked_doctype=doctype, linked_document=docname)

	payload = _fetch_messages(channel_id, limit=cint(limit) or 50, before=before or None)
	return {
		"messages": _serialize_messages(payload.get("messages")),
		"has_old_messages": payload.get("has_old_messages"),
		"has_new_messages": payload.get("has_new_messages"),
	}


@frappe.whitelist()
def send_chat_message(
	channel_id,
	text,
	is_reply=0,
	linked_message=None,
	issue_name=None,
	linked_doctype=None,
	linked_document=None,
):
	"""Send a text message as the current user (no ignore_permissions)."""
	_require_raven_feature()
	text = (text or "").strip()
	if not text:
		frappe.throw(_("Message cannot be empty"))
	if not channel_id:
		frappe.throw(_("channel_id is required"))

	doctype, docname = _resolve_linked_args(linked_doctype, linked_document, issue_name)
	_assert_linked_channel_access(channel_id, linked_doctype=doctype, linked_document=docname)

	from raven.api.raven_message import send_message

	is_reply = cint(is_reply)
	doc = send_message(
		channel_id=channel_id,
		text=text,
		is_reply=bool(is_reply),
		linked_message=linked_message if is_reply else None,
	)
	return _serialize_one_message(
		{
			"name": doc.name,
			"owner": doc.owner,
			"creation": doc.creation,
			"text": doc.text,
			"message_type": doc.message_type,
			"is_bot_message": getattr(doc, "is_bot_message", 0),
			"is_thread": getattr(doc, "is_thread", 0),
			"is_reply": getattr(doc, "is_reply", 0),
			"linked_message": getattr(doc, "linked_message", None),
			"replied_message_details": getattr(doc, "replied_message_details", None),
		}
	)


@frappe.whitelist()
def open_or_create_thread(
	message_id, issue_name=None, linked_doctype=None, linked_document=None
):
	"""Open an existing thread or create one from a channel message."""
	_require_raven_feature()
	doctype, docname = _resolve_linked_args(linked_doctype, linked_document, issue_name)
	_require_linked_read(doctype, docname)

	if not message_id:
		frappe.throw(_("message_id is required"))

	message = frappe.get_doc("Raven Message", message_id)
	parent_channel = find_linked_channel(doctype, docname)
	if not parent_channel or message.channel_id != parent_channel:
		frappe.throw(_("Message does not belong to this document's discussion"))

	if cint(message.is_thread):
		thread_id = message.name
	else:
		from raven.api.threads import create_thread

		result = create_thread(message_id)
		thread_id = result.get("thread_id") or message_id
		message.reload()

	payload = _fetch_messages(thread_id, limit=50)
	root = _serialize_one_message(
		{
			"name": message.name,
			"owner": message.owner,
			"creation": message.creation,
			"text": message.text or message.content or "",
			"message_type": message.message_type,
			"is_bot_message": message.is_bot_message,
			"is_thread": message.is_thread,
			"is_reply": message.is_reply,
			"linked_message": message.linked_message,
			"replied_message_details": message.replied_message_details,
		}
	)
	return {
		"thread_id": thread_id,
		"channel_id": parent_channel,
		"root_message": root,
		"messages": _serialize_messages(payload.get("messages")),
		"raven_url": f"/raven/channel/{thread_id}",
	}


@frappe.whitelist()
def get_thread(thread_id, issue_name=None, linked_doctype=None, linked_document=None):
	"""Refresh/poll thread overlay messages."""
	_require_raven_feature()
	doctype, docname = _resolve_linked_args(linked_doctype, linked_document, issue_name)
	_require_linked_read(doctype, docname)
	if not thread_id:
		frappe.throw(_("thread_id is required"))

	_assert_linked_channel_access(thread_id, linked_doctype=doctype, linked_document=docname)

	root_doc = None
	if frappe.db.exists("Raven Message", thread_id):
		root_doc = frappe.get_doc("Raven Message", thread_id)

	payload = _fetch_messages(thread_id, limit=50)
	root = None
	if root_doc:
		root = _serialize_one_message(
			{
				"name": root_doc.name,
				"owner": root_doc.owner,
				"creation": root_doc.creation,
				"text": root_doc.text or root_doc.content or "",
				"message_type": root_doc.message_type,
				"is_bot_message": root_doc.is_bot_message,
				"is_thread": root_doc.is_thread,
				"is_reply": root_doc.is_reply,
				"linked_message": root_doc.linked_message,
				"replied_message_details": root_doc.replied_message_details,
			}
		)

	parent_channel = find_linked_channel(doctype, docname)
	return {
		"thread_id": thread_id,
		"channel_id": parent_channel,
		"root_message": root,
		"messages": _serialize_messages(payload.get("messages")),
		"raven_url": f"/raven/channel/{thread_id}",
	}


@frappe.whitelist()
def invite_to_document_channel(linked_doctype, name, users=None):
	"""Invite extra users to the document's Raven channel."""
	_require_raven_feature()
	linked_doctype, name = _resolve_linked_args(linked_doctype, name)
	_require_linked_write(linked_doctype, name)

	channel_id = find_linked_channel(linked_doctype, name)
	if not channel_id:
		frappe.throw(_("No discussion channel yet. Start a discussion first."))

	frappe.has_permission("Raven Channel", "write", doc=channel_id, throw=True)

	raven_users = []
	skipped = []
	for user in _parse_list(users):
		ru = _user_to_raven_user(user)
		if ru:
			raven_users.append(ru)
		else:
			skipped.append(user)

	if raven_users:
		try:
			from raven.api.raven_channel_member import add_channel_members

			add_channel_members(channel_id=channel_id, members=raven_users)
		except Exception:
			_add_members(channel_id, raven_users)

	return {
		"channel_id": channel_id,
		"members": _serialize_members(channel_id),
		"skipped": skipped,
	}


@frappe.whitelist()
def invite_to_issue_channel(name, users=None):
	return invite_to_document_channel("Issue", name, users=users)


@frappe.whitelist()
def get_raven_users_for_invite():
	"""List Raven Users (type=User) for the invite picker."""
	_require_raven_feature()
	if not frappe.has_permission("Raven User", "read"):
		return []
	rows = frappe.get_all(
		"Raven User",
		filters={"type": "User", "enabled": 1},
		fields=["name", "user", "full_name"],
		order_by="full_name asc",
		limit_page_length=500,
	)
	return [
		{
			"raven_user": r.name,
			"user": r.user or r.name,
			"full_name": r.full_name or r.user or r.name,
		}
		for r in rows
	]
