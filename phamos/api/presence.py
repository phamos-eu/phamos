# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Presence helpers for the cockpit SPAs: user cards and soft field locks.

A soft field lock says "this user is typing in this field right now". It lives
in Redis only (never in the database), expires on its own after LOCK_TTL seconds
without a heartbeat, and every change is pushed to everyone who has the document
open through Frappe's realtime document room (`doc_subscribe`).

The locks are advisory for the SPA editors and enforced by the cockpit save
endpoints via `assert_fields_unlocked`, so a second cockpit user cannot
overwrite a field somebody else is editing. Desk is not affected.
"""

import re
import time

import frappe
from frappe import _
from frappe.utils import get_fullname

LOCK_TTL = 90
LOCK_EVENT = "cockpit_field_lock"
MAX_USER_CARDS = 50

# Lockable doctypes and the realtime room they are published to. Field names are
# either a plain fieldname ("description") or "<fieldname>:<child row name>" for
# child-table fields such as checklist item notes ("note:abc123").
LOCKABLE_DOCTYPES = ("Issue", "Task", "Checklist")
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,60}(:[A-Za-z0-9_-]{1,140})?$")


class FieldLockedError(frappe.ValidationError):
	"""Raised when a save touches a field another user currently holds a lock on."""


def _lock_key(doctype, name):
	return f"cockpit_field_locks|{doctype}|{name}"


def _validate_target(doctype, name, fieldname=None, ptype="write"):
	if frappe.session.user in (None, "Guest"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if doctype not in LOCKABLE_DOCTYPES:
		frappe.throw(_("Field locks are not supported for {0}").format(doctype))
	if fieldname is not None and not _FIELD_RE.match(fieldname or ""):
		frappe.throw(_("Invalid field name: {0}").format(fieldname))
	frappe.has_permission(doctype, ptype, doc=name, throw=True)


def _read_locks(doctype, name):
	"""Return {fieldname: lock} for live locks and drop expired ones."""
	cache = frappe.cache()
	key = _lock_key(doctype, name)
	try:
		raw = cache.hgetall(key) or {}
	except Exception:
		return {}

	now = time.time()
	live = {}
	for field, lock in raw.items():
		field = field.decode() if isinstance(field, bytes) else field
		if not isinstance(lock, dict) or (lock.get("expires_at") or 0) <= now:
			cache.hdel(key, field)
			continue
		live[field] = lock
	return live


def _serialize_lock(doctype, name, fieldname, lock, action):
	expires_at = (lock or {}).get("expires_at") or 0
	return {
		"doctype": doctype,
		"name": name,
		"fieldname": fieldname,
		"action": action,
		"user": (lock or {}).get("user"),
		"full_name": (lock or {}).get("full_name"),
		"user_image": (lock or {}).get("user_image"),
		"expires_in": max(0, round(expires_at - time.time())),
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
	locks = _read_locks(doctype, name)
	current = locks.get(fieldname)
	if current and current.get("user") != user:
		return {"ok": False, "lock": _serialize_lock(doctype, name, fieldname, current, "locked")}

	lock = {
		"user": user,
		"full_name": get_fullname(user) or user,
		"user_image": frappe.db.get_value("User", user, "user_image") or "",
		"expires_at": time.time() + LOCK_TTL,
	}
	cache = frappe.cache()
	key = _lock_key(doctype, name)
	cache.hset(key, fieldname, lock)
	try:
		cache.expire(cache.make_key(key), LOCK_TTL * 2)
	except Exception:
		pass

	payload = _serialize_lock(doctype, name, fieldname, lock, "locked")
	_publish(payload)
	return {"ok": True, "lock": payload}


@frappe.whitelist(methods=["POST"])
def release_field_lock(doctype, name, fieldname):
	"""Release the caller's lock on one field. Releasing someone else's lock is a no-op."""
	_validate_target(doctype, name, fieldname, ptype="read")
	current = _read_locks(doctype, name).get(fieldname)
	if not current or current.get("user") != frappe.session.user:
		return {"ok": False}

	frappe.cache().hdel(_lock_key(doctype, name), fieldname)
	_publish(_serialize_lock(doctype, name, fieldname, current, "released"))
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
	locks = _read_locks(doctype, name)
	user = frappe.session.user
	for field in fieldnames:
		lock = locks.get(field)
		if lock and lock.get("user") != user:
			frappe.throw(
				_("{0} is editing this field right now. Try again when they are done.").format(
					lock.get("full_name") or lock.get("user")
				),
				FieldLockedError,
				title=_("Field is being edited"),
			)


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
