# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Chip Space (#2053): colleagues as avatar chips on a grid.

Slice 1 (#2054) keeps the user's own chip: where it stands, saved as a user default so it is
back in the same spot after a reload, in any browser. No DocType, nothing to migrate.

Positions are in tile units but not whole tiles: the grid is drawn, movement is free.

Slice 2 (#2055), presence: who has the page open lives in the Redis cache only (a hash
user → position and last heartbeat), never in the database, and no history is kept. A heartbeat
every few seconds keeps a user online; without one for PRESENCE_TTL seconds, or after leave(),
the chip is gone. Joins, moves and leaves go out over Frappe realtime to the site room, which
only System Users join, so only System Users may use the Space.

Dummy chips for testing come from the site config, so they never appear on a site that does
not set them:

	"chip_space_dummies": [{"user": "chip-buddy@example.com", "x": 24, "y": 12}]
"""

import json
import math
import time

import frappe
from frappe import _

# One shared world for everyone; the frontend draws exactly this grid.
COLS = 40
ROWS = 25
POSITION_KEY = "phamos_chip_space_position"
DUMMIES_CONF_KEY = "chip_space_dummies"
MAX_DUMMIES = 10

PRESENCE_CACHE_KEY = "phamos_chip_space_presence"
# Seconds without a heartbeat after which a chip counts as gone (the page beats every 10 s).
PRESENCE_TTL = 45
# Moves per user: at most this many in MOVE_WINDOW seconds (the page sends about 8 a second).
MOVE_LIMIT = 60
MOVE_WINDOW = 5

EVENT_PRESENCE = "chip_space_presence"
EVENT_MOVE = "chip_space_move"
EVENT_LEAVE = "chip_space_leave"


def _require_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to use the Space."), frappe.PermissionError)
	# Realtime events reach System Users only (the site room), so nobody else could see anyone.
	if frappe.get_cached_value("User", frappe.session.user, "user_type") != "System User":
		frappe.throw(_("The Space is only available to System Users."), frappe.PermissionError)


def _clamp(value, cells):
	"""A float inside 0..cells-1, two decimals; anything that is not a finite number counts as 0."""
	try:
		value = float(value)
	except (TypeError, ValueError):
		value = 0.0
	if not math.isfinite(value):
		value = 0.0
	return round(max(0.0, min(cells - 1.0, value)), 2)


def _spawn():
	return {"x": float(COLS // 2), "y": float(ROWS // 2)}


def _stored_position():
	raw = frappe.defaults.get_user_default(POSITION_KEY)
	if not raw:
		return None
	try:
		data = json.loads(raw)
	except (TypeError, ValueError):
		return None
	if not isinstance(data, dict):
		return None
	return {"x": _clamp(data.get("x"), COLS), "y": _clamp(data.get("y"), ROWS)}


def _chip(user, position):
	full_name, user_image = frappe.db.get_value("User", user, ["full_name", "user_image"]) or ("", "")
	return {**position, "user": user, "full_name": full_name or user, "user_image": user_image or ""}


def _dummies(me):
	"""Test chips from the site config: existing, enabled users other than me."""
	entries = frappe.conf.get(DUMMIES_CONF_KEY) or []
	if not isinstance(entries, list):
		return []
	chips = []
	for entry in entries[:MAX_DUMMIES]:
		if not isinstance(entry, dict):
			continue
		user = entry.get("user")
		if not isinstance(user, str) or user == me or not frappe.db.get_value("User", user, "enabled"):
			continue
		chips.append(_chip(user, {"x": _clamp(entry.get("x"), COLS), "y": _clamp(entry.get("y"), ROWS), "dummy": True}))
	return chips


def _online(exclude=None):
	"""Chips of users with a recent heartbeat; stale entries are dropped on the way."""
	now = time.time()
	chips = []
	for user, entry in (frappe.cache.hgetall(PRESENCE_CACHE_KEY) or {}).items():
		user = frappe.safe_decode(user)
		if not isinstance(entry, dict) or now - entry.get("ts", 0) > PRESENCE_TTL:
			frappe.cache.hdel(PRESENCE_CACHE_KEY, user)
			continue
		if user != exclude:
			chips.append({k: v for k, v in entry.items() if k != "ts"})
	return chips


def _publish(event, message):
	# No user and no room: the site room, i.e. every System User's open cockpit tab.
	frappe.publish_realtime(event, message, after_commit=False)


def _throttled():
	"""True when this user sent more than MOVE_LIMIT moves in the current window."""
	# incrby/expire are plain redis calls: the key needs the site prefix itself.
	key = frappe.cache.make_key(f"phamos_chip_space_moves:{frappe.session.user}")
	count = frappe.cache.incrby(key, 1)
	if count == 1:
		frappe.cache.expire(key, MOVE_WINDOW)
	return count > MOVE_LIMIT


@frappe.whitelist()
def get_space():
	"""The grid size, my chip (where it stands, or the spawn) and the other chips."""
	_require_user()
	user = frappe.session.user
	dummies = _dummies(user)
	dummy_users = {d["user"] for d in dummies}
	return {
		"cols": COLS,
		"rows": ROWS,
		"me": {**_chip(user, _stored_position() or _spawn()), "cols": COLS, "rows": ROWS},
		"others": dummies + [c for c in _online(exclude=user) if c["user"] not in dummy_users],
		"presence_ttl": PRESENCE_TTL,
	}


@frappe.whitelist(methods=["POST"])
def heartbeat(x, y):
	"""I am here (join, and every few seconds while the page is open), standing at x, y."""
	_require_user()
	user = frappe.session.user
	chip = _chip(user, {"x": _clamp(x, COLS), "y": _clamp(y, ROWS)})
	frappe.cache.hset(PRESENCE_CACHE_KEY, user, {**chip, "ts": time.time()})
	_publish(EVENT_PRESENCE, chip)
	return chip


@frappe.whitelist(methods=["POST"])
def move(x, y):
	"""Tell the others where my chip is now. Only for a chip that is present (heartbeat first)."""
	_require_user()
	user = frappe.session.user
	entry = frappe.cache.hget(PRESENCE_CACHE_KEY, user)
	if not isinstance(entry, dict) or _throttled():
		return None
	entry.update({"x": _clamp(x, COLS), "y": _clamp(y, ROWS), "ts": time.time()})
	frappe.cache.hset(PRESENCE_CACHE_KEY, user, entry)
	message = {"user": user, "x": entry["x"], "y": entry["y"]}
	_publish(EVENT_MOVE, message)
	return message


@frappe.whitelist(methods=["POST"])
def leave():
	"""I closed the page: my chip disappears for everyone right away."""
	_require_user()
	user = frappe.session.user
	frappe.cache.hdel(PRESENCE_CACHE_KEY, user)
	_publish(EVENT_LEAVE, {"user": user})


@frappe.whitelist(methods=["POST"])
def save_my_position(x, y):
	"""Remember where my chip stands; values outside the grid are moved onto its edge."""
	_require_user()
	position = {"x": _clamp(x, COLS), "y": _clamp(y, ROWS)}
	frappe.defaults.set_user_default(POSITION_KEY, json.dumps(position, separators=(",", ":")))
	return position
