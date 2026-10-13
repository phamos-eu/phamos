# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Presence helpers for the cockpit SPAs: user cards and soft field locks.

A soft field lock says "this user is typing in this field right now". It lives
in Redis only (never in the database) as one key per field, is taken atomically,
expires on its own after LOCK_TTL seconds without a heartbeat, and every change is pushed to everyone who has the document
open through Frappe's realtime document room (`doc_subscribe`).

The locks are advisory for the SPA editors and enforced by the cockpit save
endpoints via `assert_fields_unlocked`, so a second cockpit user cannot
overwrite a field somebody else is editing. Desk is not affected.
"""

import re

import frappe
from frappe import _
from frappe.utils import get_fullname

# Seconds a lock survives without a heartbeat (the client renews every 10 s).
LOCK_TTL = 30
LOCK_EVENT = "cockpit_field_lock"
MAX_USER_CARDS = 50

# Lockable doctypes and the realtime room they are published to. Field names are
# either a plain fieldname ("description") or "<fieldname>:<child row name>" for
# child-table fields such as checklist item notes ("note:abc123").
LOCKABLE_DOCTYPES = ("Issue", "Task", "Checklist")
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,60}(:[A-Za-z0-9_-]{1,140})?$")


class FieldLockedError(frappe.ValidationError):
	"""Raised when a save touches a field another user currently holds a lock on."""


# Each lock is its own Redis key holding the user id, with a TTL. A per-document
# set indexes which fields have a key, so locks can be listed without SCAN.
# Check-and-write runs as a Lua script: Redis executes it atomically, so two
# users focusing the same field at the same moment cannot both get the lock.
_ACQUIRE_SCRIPT = """
local holder = redis.call('GET', KEYS[1])
if holder and holder ~= ARGV[1] then return holder end
redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[2]))
redis.call('SADD', KEYS[2], ARGV[3])
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[2]) * 2)
return ARGV[1]
"""

# Delete only if the caller still holds the lock (it may have expired and been
# taken by someone else in the meantime).
_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
	redis.call('DEL', KEYS[1])
	redis.call('SREM', KEYS[2], ARGV[2])
	return 1
end
return 0
"""


def _field_key(doctype, name, fieldname):
	return frappe.cache().make_key(f"cockpit_field_lock|{doctype}|{name}|{fieldname}")


def _index_key(doctype, name):
	return frappe.cache().make_key(f"cockpit_field_lock_index|{doctype}|{name}")


def _decode(value):
	return value.decode() if isinstance(value, bytes) else value


def _validate_target(doctype, name, fieldname=None, ptype="write"):
	if frappe.session.user in (None, "Guest"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if doctype not in LOCKABLE_DOCTYPES:
		frappe.throw(_("Field locks are not supported for {0}").format(doctype))
	if fieldname is not None and not _FIELD_RE.match(fieldname or ""):
		frappe.throw(_("Invalid field name: {0}").format(fieldname))
	frappe.has_permission(doctype, ptype, doc=name, throw=True)


def _read_locks(doctype, name, fieldnames=None):
	"""Return {fieldname: {"user", "expires_in"}} for live locks.

	Without `fieldnames` all indexed fields of the document are read; index
	entries whose key has expired are removed on the way.
	"""
	cache = frappe.cache()
	index = _index_key(doctype, name)
	try:
		if fieldnames is None:
			fieldnames = [_decode(f) for f in cache.execute_command("SMEMBERS", index)]
		live = {}
		for field in fieldnames:
			key = _field_key(doctype, name, field)
			user = _decode(cache.execute_command("GET", key))
			if not user:
				cache.execute_command("SREM", index, field)
				continue
			ttl_ms = cache.execute_command("PTTL", key) or 0
			live[field] = {"user": user, "expires_in": max(0, round(ttl_ms / 1000))}
		return live
	except Exception:
		# Redis unavailable: locks are advisory, so fail open rather than block saves.
		frappe.log_error(title="Cockpit field locks: Redis unavailable")
		return {}


def _serialize_lock(doctype, name, fieldname, lock, action):
	user = (lock or {}).get("user")
	return {
		"doctype": doctype,
		"name": name,
		"fieldname": fieldname,
		"action": action,
		"user": user,
		"full_name": (get_fullname(user) or user) if user else None,
		"user_image": (frappe.db.get_value("User", user, "user_image") or "") if user else "",
		"expires_in": (lock or {}).get("expires_in", 0),
	}


def _publish(payload):
	frappe.publish_realtime(
		LOCK_EVENT,
		payload,
		doctype=payload["doctype"],
		docname=payload["name"],
	)


@frappe.whitelist(methods=["POST"])
def acquire_field_lock(doctype, name, fieldname):
	"""Take (or refresh) the lock on one field. Also serves as the heartbeat.

	Returns {"ok": True, "lock": ...} or {"ok": False, "lock": <holder>} when
	another user holds a live lock on the same field.
	"""
	_validate_target(doctype, name, fieldname)
	user = frappe.session.user
	try:
		holder = _decode(
			frappe.cache().eval(
				_ACQUIRE_SCRIPT,
				2,
				_field_key(doctype, name, fieldname),
				_index_key(doctype, name),
				user,
				LOCK_TTL,
				fieldname,
			)
		)
	except Exception:
		frappe.log_error(title="Cockpit field locks: Redis unavailable")
		return {"ok": True, "lock": None}

	if holder != user:
		current = _read_locks(doctype, name, [fieldname]).get(fieldname) or {"user": holder}
		return {"ok": False, "lock": _serialize_lock(doctype, name, fieldname, current, "locked")}

	payload = _serialize_lock(
		doctype, name, fieldname, {"user": user, "expires_in": LOCK_TTL}, "locked"
	)
	_publish(payload)
	return {"ok": True, "lock": payload}


@frappe.whitelist(methods=["POST"])
def release_field_lock(doctype, name, fieldname):
	"""Release the caller's lock on one field. Releasing someone else's lock is a no-op."""
	_validate_target(doctype, name, fieldname, ptype="read")
	user = frappe.session.user
	try:
		released = frappe.cache().eval(
			_RELEASE_SCRIPT,
			2,
			_field_key(doctype, name, fieldname),
			_index_key(doctype, name),
			user,
			fieldname,
		)
	except Exception:
		frappe.log_error(title="Cockpit field locks: Redis unavailable")
		return {"ok": False}
	if not released:
		return {"ok": False}

	_publish(_serialize_lock(doctype, name, fieldname, {"user": user}, "released"))
	return {"ok": True}


@frappe.whitelist()
def get_field_locks(doctype, name):
	"""Return the live locks on a document (all users, including the caller)."""
	_validate_target(doctype, name, ptype="read")
	return [
		_serialize_lock(doctype, name, field, lock, "locked")
		for field, lock in _read_locks(doctype, name).items()
	]


def assert_fields_unlocked(doctype, name, fieldnames):
	"""Throw FieldLockedError if any of `fieldnames` is locked by another user."""
	fieldnames = [f for f in (fieldnames or []) if f]
	if not fieldnames:
		return
	user = frappe.session.user
	for lock in _read_locks(doctype, name, fieldnames).values():
		if lock["user"] != user:
			frappe.throw(
				_("{0} is editing this field right now. Try again when they are done.").format(
					get_fullname(lock["user"]) or lock["user"]
				),
				FieldLockedError,
				title=_("Field is being edited"),
			)


def clear_field_locks(doctype, name):
	"""Drop every lock on a document (tests and manual clean-up)."""
	cache = frappe.cache()
	index = _index_key(doctype, name)
	for field in cache.execute_command("SMEMBERS", index) or []:
		cache.execute_command("DEL", _field_key(doctype, name, _decode(field)))
	cache.execute_command("DEL", index)


@frappe.whitelist()
def get_user_cards(users):
	"""Name, full name and image for the given users (presence avatars).

	Resolved server-side because Desk users other than System Managers may not
	read the User doctype. Only desk (System) users can call it or be listed.
	"""
	if frappe.session.user in (None, "Guest") or (
		frappe.session.user != "Administrator"
		and frappe.get_cached_value("User", frappe.session.user, "user_type") != "System User"
	):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if isinstance(users, str):
		users = frappe.parse_json(users) if users.strip().startswith("[") else [users]
	users = [u for u in (users or []) if isinstance(u, str) and u][:MAX_USER_CARDS]
	if not users:
		return []
	rows = frappe.get_all(
		"User",
		filters={"name": ("in", users), "enabled": 1, "user_type": "System User"},
		fields=["name", "full_name", "user_image"],
		ignore_permissions=True,
	)
	by_name = {r.name: r for r in rows}
	return [
		{
			"name": u,
			"full_name": by_name[u].full_name or u,
			"user_image": by_name[u].user_image or "",
		}
		for u in users
		if u in by_name
	]
