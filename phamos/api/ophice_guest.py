# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Guests in Ophice (phamos/phamos#2080, #2082): external people on the map, without an account.

Everything here is reachable without login (allow_guest), so it stays small and checks its own:
- a guest comes in through the public link, passes a small "I am human" check and gives a name;
- the guest session lives in Redis (name, expiry) and in a signed cookie; nothing goes into the
  database;
- a guest moves only inside the guest area (the server clamps every position) and sees only the
  chips there; the rest of the map is blurred on their page.
Employees see guests as chips in the normal presence list ("guest": True).
"""

import hashlib
import hmac
import json
import random
import re
import time

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import strip_html

from phamos.api import ophice

GUEST_CACHE_KEY = "phamos_ophice_guests"
CHECK_CACHE_PREFIX = "phamos_ophice_guest_check:"
COOKIE = "ophice_guest"
SESSION_SECONDS = 12 * 60 * 60
MAX_GUESTS = 25
NAME_LENGTH = 40
# The human check: drag your chip through the entrance. Not before this many seconds, within
# this distance of the entrance (0..1 of the track), with at least this many pointer samples.
CHECK_MIN_SECONDS = 1.0
CHECK_TTL = 300
CHECK_TOLERANCE = 0.07
CHECK_MIN_SAMPLES = 6
# Moves per guest and second the server takes (more are dropped, the page sends at most ~7).
MOVE_LIMIT = 15
GUEST_PREFIX = "guest:"
# A visit without a heartbeat for this long ends (review of the develop release): a closed tab
# frees its place for the next guest well before the 12 hours.
IDLE_SECONDS = 30 * 60
# The heartbeat writes "seen" at most this often (the page asks every second).
SEEN_EVERY = 60
# The human check's pointer path: at most this many samples are read.
CHECK_MAX_SAMPLES = 200


# --- Session


def _sign(guest_id):
	from frappe.utils.password import get_encryption_key

	return hmac.new(get_encryption_key().encode(), guest_id.encode(), hashlib.sha256).hexdigest()[:32]


def _token(guest_id):
	return f"{guest_id}.{_sign(guest_id)}"


def _expired(entry, now=None):
	"""Over: the 12 hours are up, or the page has not called for IDLE_SECONDS."""
	now = now or time.time()
	if not isinstance(entry, dict) or entry.get("expires", 0) < now:
		return True
	return now - entry.get("seen", now) > IDLE_SECONDS


def _end_visit(guest_id, publish=True):
	"""Everything of a visit goes: session, invite, chip. Nothing about it stays in Redis."""
	frappe.cache.hdel(GUEST_CACHE_KEY, guest_id)
	frappe.cache.hdel(INVITE_CACHE_KEY, guest_id)
	frappe.cache.hdel(ophice.PRESENCE_CACHE_KEY, GUEST_PREFIX + guest_id)
	if publish:
		ophice._publish(ophice.EVENT_LEAVE, {"user": GUEST_PREFIX + guest_id})


def _sessions():
	"""Live guest sessions {guest_id: entry}; ended ones are dropped on the way."""
	now = time.time()
	live = {}
	for guest_id, entry in (frappe.cache.hgetall(GUEST_CACHE_KEY) or {}).items():
		guest_id = frappe.safe_decode(guest_id)
		if _expired(entry, now):
			_end_visit(guest_id)
			continue
		live[guest_id] = entry
	return live


def purge_guests():
	"""Scheduler (every minute): ended visits and invites without a visit are removed, also when
	no new guest comes in. Guest data must not stay in Redis (GDPR)."""
	live = _sessions()
	for guest_id in list((frappe.cache.hgetall(INVITE_CACHE_KEY) or {}).keys()):
		guest_id = frappe.safe_decode(guest_id)
		if guest_id not in live:
			frappe.cache.hdel(INVITE_CACHE_KEY, guest_id)


def _current_guest():
	"""(guest_id, entry) of this request's guest session, or (None, None)."""
	token = getattr(frappe.local, "ophice_guest_token", None)
	if not token and getattr(frappe.local, "request", None):
		token = frappe.request.cookies.get(COOKIE)
	if not token or "." not in token:
		return None, None
	guest_id, signature = token.rsplit(".", 1)
	if not hmac.compare_digest(signature, _sign(guest_id)):
		return None, None
	entry = frappe.cache.hget(GUEST_CACHE_KEY, guest_id)
	if _expired(entry):
		return None, None
	return guest_id, entry


def _require_guest():
	guest_id, entry = _current_guest()
	if not guest_id:
		frappe.throw(_("Your visit has ended. Please come in again."), frappe.PermissionError)
	return guest_id, entry


def _set_cookie(token, seconds):
	manager = getattr(frappe.local, "cookie_manager", None)
	if manager:
		manager.set_cookie(
			COOKIE,
			token,
			expires=frappe.utils.add_to_date(None, seconds=seconds),
			httponly=True,
			samesite="Lax",
		)
	# Within this request (and in tests) the session counts at once.
	frappe.local.ophice_guest_token = token


# --- Where a guest may be


def guest_area():
	return next((a for a in ophice._areas() if a.kind == "Guest"), None)


def allowed_areas(guest_id):
	"""The areas this guest may stand in: the guest area, plus the customer meeting area of an
	accepted invite (#2084)."""
	area = guest_area()
	areas = [area] if area else []
	invite = _invite(guest_id)
	if invite and invite["status"] in ("accepted", "arrived"):
		meeting = next((a for a in ophice._areas() if a.name == invite["area"]), None)
		if meeting:
			areas.append(meeting)
	return areas


def _corridor(guest_id):
	"""The way to the pin while walking there (#2084): a band along the straight line, this guest only."""
	invite = _invite(guest_id)
	if invite and invite["status"] == "accepted" and invite.get("corridor"):
		return invite["corridor"]
	return None


def _inside(area, x, y):
	cx, cy = x + 0.5, y + 0.5
	return area.x <= cx <= area.x + area.width and area.y <= cy <= area.y + area.height


def clamp_to(areas, x, y, corridor=None):
	"""The nearest position whose chip centre lies inside one of the areas (or the corridor).

	x and y come from the guest's page: anything that is not a finite number on the grid (NaN,
	Infinity, text) is made one first, so no NaN reaches the presence list everyone reads."""
	x, y = ophice._clamp(x, ophice._cols()), ophice._clamp(y, ophice._rows())
	px, py = x + 0.5, y + 0.5
	candidates = []
	for area in areas:
		candidates.append((min(max(px, area.x), area.x + area.width), min(max(py, area.y), area.y + area.height)))
	if corridor:
		candidates.append(_onto_band(corridor, px, py))
	if not candidates:
		return x, y
	cx, cy = min(candidates, key=lambda c: (c[0] - px) ** 2 + (c[1] - py) ** 2)
	return round(cx - 0.5, 2), round(cy - 0.5, 2)


def _onto_band(corridor, px, py):
	"""The nearest point within `radius` of the segment from -> to (chip centres)."""
	ax, ay = corridor["from"]
	bx, by = corridor["to"]
	dx, dy = bx - ax, by - ay
	length = dx * dx + dy * dy
	t = 0.0 if not length else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
	qx, qy = ax + t * dx, ay + t * dy
	distance = ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5
	radius = corridor.get("radius", CORRIDOR_RADIUS)
	if distance <= radius:
		return px, py
	return qx + (px - qx) * radius / distance, qy + (py - qy) * radius / distance


def _rect(area):
	return {"name": area.name, "title": area.title, "x": area.x, "y": area.y, "width": area.width, "height": area.height}


# --- Presence


def _guest_chip(guest_id, entry, x, y):
	return {
		"user": GUEST_PREFIX + guest_id,
		"full_name": entry["name"],
		"user_image": "",
		"status": None,
		"guest": True,
		"x": x,
		"y": y,
	}


def _put(guest_id, entry, x, y, publish_event=None, beam=False):
	chip = _guest_chip(guest_id, entry, x, y)
	frappe.cache.hset(ophice.PRESENCE_CACHE_KEY, chip["user"], {**chip, "ts": time.time()})
	if publish_event == ophice.EVENT_PRESENCE:
		ophice._publish(ophice.EVENT_PRESENCE, {**chip, "beam": True} if beam else chip)
	elif publish_event == ophice.EVENT_MOVE:
		ophice._publish(ophice.EVENT_MOVE, {"user": chip["user"], "x": x, "y": y})
	return chip


def _throttled(guest_id):
	key = frappe.cache.make_key(f"phamos_ophice_guest_moves:{guest_id}")
	count = frappe.cache.incrby(key, 1)
	if count == 1:
		frappe.cache.expire(key, 1)
	return count > MOVE_LIMIT


# --- Endpoints (no login)


@frappe.whitelist(allow_guest=True)
def guest_info():
	"""Before the check: is there a guest area to come into?"""
	area = guest_area()
	return {"open": bool(area), "title": area.title if area else ""}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=600)
def start_check():
	"""A new "I am human" task: drag the chip to the entrance at `door` (0..1 along the track)."""
	challenge = frappe.generate_hash(length=24)
	door = round(random.uniform(0.2, 0.85), 3)
	frappe.cache.set_value(CHECK_CACHE_PREFIX + challenge, {"door": door, "issued": time.time()}, expires_in_sec=CHECK_TTL)
	return {"challenge": challenge, "door": door}


def _passes_check(challenge, x, path):
	"""The chip was dragged (not set) to the entrance, after a human-ish while. Single use."""
	if not isinstance(challenge, str) or not re.fullmatch(r"[0-9a-f]{24}", challenge):
		return False
	key = CHECK_CACHE_PREFIX + challenge
	data = frappe.cache.get_value(key)
	frappe.cache.delete_value(key)
	if not isinstance(data, dict) or time.time() - data["issued"] < CHECK_MIN_SECONDS:
		return False
	try:
		x = float(x)
		samples = json.loads(path) if isinstance(path, str) else path
		points = [(float(p[0]), float(p[1])) for p in list(samples)[:CHECK_MAX_SAMPLES]]
	except (TypeError, ValueError, IndexError):
		return False
	if abs(x - data["door"]) > CHECK_TOLERANCE or len(points) < CHECK_MIN_SAMPLES:
		return False
	times = [t for _x, t in points]
	# A drag takes time and moves step by step; a script that posts one jump does not.
	return times == sorted(times) and times[-1] - times[0] >= 300 and len({round(p, 2) for p, _t in points}) >= 4


def _clean_name(name):
	name = re.sub(r"\s+", " ", strip_html(name or "")).strip()[:NAME_LENGTH]
	if len(name) < 2:
		frappe.throw(_("Please tell us your name."))
	return name


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=600)
def enter(name, challenge, x, path):
	"""Come in: check passed, name given → a guest session, beamed into the guest area."""
	if frappe.session.user != "Guest":
		frappe.throw(_("You are logged in: please use Ophice as an employee."))
	name = _clean_name(name)
	if not _passes_check(challenge, x, path):
		frappe.throw(_("That did not work. Please drag your chip to the entrance again."))
	area = guest_area()
	if not area:
		frappe.throw(_("Ophice has no guest area at the moment."))
	# Visits that are live right now (a closed tab ends after IDLE_SECONDS), not every visit of
	# the last 12 hours: one person cannot lock the door for half a day.
	if len(_sessions()) >= MAX_GUESTS:
		frappe.throw(_("Ophice is full right now. Please try again in a few minutes."))
	guest_id = frappe.generate_hash(length=20)
	now = time.time()
	entry = {"name": name, "expires": now + SESSION_SECONDS, "seen": now}
	frappe.cache.hset(GUEST_CACHE_KEY, guest_id, entry)
	_set_cookie(_token(guest_id), SESSION_SECONDS)
	spot = ophice._free_spot(area, GUEST_PREFIX + guest_id)
	_put(guest_id, entry, spot["x"], spot["y"], publish_event=ophice.EVENT_PRESENCE, beam=True)
	return {**guest_space(), "beam_in": True}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def guest_space():
	"""My chip, where I may go, and the chips there. Also my heartbeat (the page asks every second)."""
	guest_id, entry = _require_guest()
	areas = allowed_areas(guest_id)
	if not areas:
		# The guest area was removed: there is nowhere a guest may stand, so the visit ends.
		_end_visit(guest_id)
		frappe.throw(_("Ophice has no guest area at the moment."), frappe.PermissionError)
	now = time.time()
	if now - entry.get("seen", 0) > SEEN_EVERY:
		entry["seen"] = now
		frappe.cache.hset(GUEST_CACHE_KEY, guest_id, entry)
	me = frappe.cache.hget(ophice.PRESENCE_CACHE_KEY, GUEST_PREFIX + guest_id)
	if isinstance(me, dict):
		x, y = clamp_to(areas, me["x"], me["y"], _corridor(guest_id))
		# Pulled back (invite taken back, area changed): the employees see it at once.
		event = ophice.EVENT_MOVE if (x, y) != (me["x"], me["y"]) else None
	else:
		spot = ophice._free_spot(areas[0], GUEST_PREFIX + guest_id)
		x, y = spot["x"], spot["y"]
		event = ophice.EVENT_PRESENCE
	chip = _put(guest_id, entry, x, y, publish_event=event)
	_check_arrival(guest_id, x, y)
	# Only chips inside my areas: nothing about anyone elsewhere in the office. Employees appear
	# under an opaque id, never their user id (their e-mail address).
	others = [
		{**{k: c.get(k) for k in ("full_name", "user_image", "x", "y", "guest")}, "user": public_id(c["user"])}
		for c in ophice._online(exclude=chip["user"])
		if any(_inside(a, c["x"], c["y"]) for a in areas)
	]
	background = ophice._background()
	return {
		"cols": ophice._cols(),
		"rows": ophice._rows(),
		"me": chip,
		"areas": [_rect(a) for a in areas],
		"others": others,
		"background": background.get("url") or "",
		"background_layout": ophice._background_layout(background),
		"background_ratio": ophice._background_ratio(background),
		"expires_in": max(0, round(entry["expires"] - time.time())),
		# The meeting and chat where I stand (#2083); the page asks every second.
		"room": _chat_for_guest(guest_id, chip, areas),
		# An invite to a customer meeting (#2084): its pin and the way there.
		"invite": _invite_for_guest(guest_id),
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def guest_move(x, y):
	"""I walked: the position is kept inside my areas and shown to the employees."""
	guest_id, entry = _require_guest()
	if _throttled(guest_id):
		return None
	x, y = clamp_to(allowed_areas(guest_id), x, y, _corridor(guest_id))
	_put(guest_id, entry, x, y, publish_event=ophice.EVENT_MOVE)
	_check_arrival(guest_id, x, y)
	return {"x": x, "y": y}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def guest_leave():
	"""I closed the page: the visit ends, my chip disappears."""
	guest_id, _entry = _current_guest()
	if not guest_id:
		return False
	_end_visit(guest_id)
	_set_cookie("", 1)
	return True


def public_id(user):
	"""What a guest sees instead of an employee's user id (their e-mail address): a stable,
	opaque id. Guests keep their own "guest:<id>"."""
	if not user or user.startswith(GUEST_PREFIX):
		return user
	return "staff:" + _sign("staff:" + user)[:16]


@frappe.whitelist(methods=["POST"])
def send_guest_out(guest):
	"""Employees: end a guest's visit (a wrong name, someone who should not be there)."""
	ophice._require_user()
	guest_id, _entry = _guest_of(guest)
	_end_visit(guest_id)
	return True


def online_guests():
	"""For employees: the guests on the map now, as people-list rows."""
	area = guest_area()
	rows = []
	for chip in ophice._online():
		if chip.get("guest"):
			rows.append(
				{
					"user": chip["user"],
					"full_name": chip["full_name"],
					"user_image": "",
					"online": True,
					"hidden": False,
					"guest": True,
					"status": None,
					"area": area.title if area and _inside(area, chip["x"], chip["y"]) else "",
				}
			)
	return rows


# --- Guest chat (#2083): in the guest area and customer meeting areas, for everyone standing
# there, guests and employees. Only in Redis: a list per area that expires CHAT_TTL after the
# last person left (every read or message by someone inside keeps it alive). Never in Raven or
# the database; saving is a mail draft in the person's own mail program.

CHAT_KEY_PREFIX = "phamos_ophice_guest_chat:"
CHAT_TTL = 10 * 60
CHAT_KEEP = 200
CHAT_SHOWN = 100
CHAT_TEXT_LENGTH = 1000
GUEST_CHAT_KINDS = ("Guest", "Customer meeting")
EVENT_GUEST_CHAT = "ophice_guest_chat"


def _chat_key(area_name):
	# Frappe's list calls (rpush, lrange, ltrim) add the site prefix themselves; expire does not.
	return CHAT_KEY_PREFIX + area_name


def _keep_alive(area_name):
	frappe.cache.expire(frappe.cache.make_key(_chat_key(area_name)), CHAT_TTL)


def _read_chat(area_name):
	key = _chat_key(area_name)
	rows = frappe.cache.lrange(key, -CHAT_SHOWN, -1) or []
	if rows:
		_keep_alive(area_name)
	messages = []
	for raw in rows:
		try:
			messages.append(json.loads(frappe.safe_decode(raw)))
		except ValueError:
			continue
	return messages


def _add_message(area, owner, author, text, guest):
	text = (text or "").strip()
	if not text:
		frappe.throw(_("Write something first."))
	message = {
		"name": frappe.generate_hash(length=12),
		"owner": owner,
		"author": author,
		"guest": bool(guest),
		"text": text[:CHAT_TEXT_LENGTH],
		"ts": time.time(),
	}
	key = _chat_key(area.name)
	frappe.cache.rpush(key, json.dumps(message))
	frappe.cache.ltrim(key, -CHAT_KEEP, -1)
	_keep_alive(area.name)
	# Employees in the area get it live; guests get it with their next poll (every second).
	for chip in ophice._online():
		if not chip.get("guest") and _inside(area, chip["x"], chip["y"]):
			frappe.publish_realtime(EVENT_GUEST_CHAT, {"area": area.name, "message": message}, user=chip["user"])
	return message


def _guest_chat_area_of(x, y, areas):
	return next((a for a in areas if a.kind in GUEST_CHAT_KINDS and _inside(a, x, y)), None)


def _chat_for_guest(guest_id, chip, areas):
	"""The meeting and chat of the area the guest stands in (for guest_space).

	A guest reads only what was written since they stepped into that area: an earlier visitor's
	conversation is not for the next one. Leaving the area resets it."""
	area = _guest_chat_area_of(chip["x"], chip["y"], areas)
	entry = frappe.cache.hget(GUEST_CACHE_KEY, guest_id)
	if not isinstance(entry, dict):
		return None
	since = entry.get("chat_since") or {}
	if not area:
		if since:
			entry["chat_since"] = {}
			frappe.cache.hset(GUEST_CACHE_KEY, guest_id, entry)
		return None
	if area.name not in since:
		entry["chat_since"] = {area.name: time.time()}
		frappe.cache.hset(GUEST_CACHE_KEY, guest_id, entry)
	start = entry["chat_since"][area.name]
	messages = [
		{**m, "owner": public_id(m.get("owner"))} for m in _read_chat(area.name) if m.get("ts", 0) >= start
	]
	return {
		"area": area.name,
		"title": area.title,
		"jitsi_domain": area.jitsi_domain,
		"jitsi_room": area.jitsi_room,
		"messages": messages,
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def guest_send(text):
	"""A guest writes into the chat of the area they stand in."""
	guest_id, entry = _require_guest()
	key = frappe.cache.make_key(f"phamos_ophice_guest_sends:{guest_id}")
	if frappe.cache.incrby(key, 1) > 5:
		frappe.throw(_("Not so fast, please."))
	frappe.cache.expire(key, 5)
	me = frappe.cache.hget(ophice.PRESENCE_CACHE_KEY, GUEST_PREFIX + guest_id)
	area = _guest_chat_area_of(me["x"], me["y"], allowed_areas(guest_id)) if isinstance(me, dict) else None
	if not area:
		frappe.throw(_("Step into the area to chat."))
	message = _add_message(area, GUEST_PREFIX + guest_id, entry["name"], strip_html(text or ""), guest=True)
	return {**message, "owner": public_id(message["owner"])}


def _employee_area(area_name):
	ophice._require_user()
	area = ophice._area(area_name)
	if area.kind not in GUEST_CHAT_KINDS:
		frappe.throw(_("This space has no guest chat."))
	if not ophice._inside_area(area, frappe.session.user):
		frappe.throw(_("Step into the area to use its chat."), frappe.PermissionError)
	return area


@frappe.whitelist()
def get_guest_chat(area):
	"""Employees: the guest chat of the guest or customer meeting area I stand in."""
	doc = _employee_area(area)
	return {"area": doc.name, "messages": _read_chat(doc.name)}


@frappe.whitelist(methods=["POST"])
def send_guest_chat(area, text):
	"""Employees: write into the guest chat of the area I stand in."""
	doc = _employee_area(area)
	return _add_message(doc, frappe.session.user, frappe.utils.get_fullname(frappe.session.user), text, guest=False)


# --- Invites to a customer meeting (#2084). An employee invites a guest; a pin is set in the
# customer meeting area. When the guest accepts, a corridor along the straight line from where
# they stand to the pin opens for them only; their chip walks there by itself (they can take over).
# On arrival the corridor closes; the guest stays free to move in the guest area and that room.
# Kept in Redis next to the guest session; it ends with the visit.

INVITE_CACHE_KEY = "phamos_ophice_guest_invites"
CORRIDOR_RADIUS = 0.75
EVENT_INVITE_ANSWER = "ophice_guest_invite_answer"


def _invite(guest_id):
	invite = frappe.cache.hget(INVITE_CACHE_KEY, guest_id)
	return invite if isinstance(invite, dict) else None


def _guest_of(guest):
	"""The guest id of a chip "guest:<id>" with a live session, or a clear error."""
	guest_id = (guest or "").removeprefix(GUEST_PREFIX)
	entry = frappe.cache.hget(GUEST_CACHE_KEY, guest_id) if guest_id else None
	if _expired(entry):
		frappe.throw(_("This guest has left."))
	return guest_id, entry


def _invite_for_guest(guest_id):
	invite = _invite(guest_id)
	if not invite:
		return None
	return {k: invite.get(k) for k in ("status", "by_name", "area", "area_title", "pin", "corridor")}


@frappe.whitelist()
def get_customer_rooms(guest):
	"""Employees: where I can invite this guest, and the invite that is open for them."""
	ophice._require_user()
	guest_id, entry = _guest_of(guest)
	rooms = [{"name": a.name, "title": a.title} for a in ophice._areas() if a.kind == "Customer meeting"]
	return {"guest": entry["name"], "rooms": rooms, "invite": _invite_for_guest(guest_id)}


@frappe.whitelist(methods=["POST"])
def invite_guest(guest, area):
	"""Employees: invite a guest to a customer meeting area. A pin is set in its middle; the guest decides."""
	ophice._require_user()
	guest_id, entry = _guest_of(guest)
	room = ophice._area(area)
	if room.kind != "Customer meeting":
		frappe.throw(_("Guests can only be invited to a customer meeting area."))
	# The pin sits in the middle of the room (PM, 2026-11-22); chips are drawn one tile wide.
	pin = {"x": round(room.x + room.width / 2 - 0.5, 2), "y": round(room.y + room.height / 2 - 0.5, 2)}
	invite = {
		"status": "pending",
		"area": room.name,
		"area_title": room.title,
		"pin": {"x": pin["x"], "y": pin["y"]},
		"by": frappe.session.user,
		"by_name": frappe.utils.get_fullname(frappe.session.user),
		"created": time.time(),
	}
	frappe.cache.hset(INVITE_CACHE_KEY, guest_id, invite)
	return _invite_for_guest(guest_id)


@frappe.whitelist(methods=["POST"])
def withdraw_invite(guest):
	"""Employees: take an invite back. A guest on the way is pulled back to where they may be."""
	ophice._require_user()
	guest_id, _entry = _guest_of(guest)
	frappe.cache.hdel(INVITE_CACHE_KEY, guest_id)
	return True


@frappe.whitelist(allow_guest=True, methods=["POST"])
def answer_invite(accept):
	"""A guest accepts or declines. Accept opens the corridor from where they stand to the pin."""
	guest_id, entry = _require_guest()
	invite = _invite(guest_id)
	if not invite or invite["status"] != "pending":
		frappe.throw(_("This invite is no longer open."))
	accepted = frappe.utils.cint(accept) == 1
	if accepted:
		me = frappe.cache.hget(ophice.PRESENCE_CACHE_KEY, GUEST_PREFIX + guest_id) or {}
		x = ophice._clamp(me.get("x", invite["pin"]["x"]), ophice._cols())
		y = ophice._clamp(me.get("y", invite["pin"]["y"]), ophice._rows())
		start = (x + 0.5, y + 0.5)
		end = (invite["pin"]["x"] + 0.5, invite["pin"]["y"] + 0.5)
		invite.update({"status": "accepted", "corridor": {"from": start, "to": end, "radius": CORRIDOR_RADIUS}})
		frappe.cache.hset(INVITE_CACHE_KEY, guest_id, invite)
	else:
		frappe.cache.hdel(INVITE_CACHE_KEY, guest_id)
	frappe.publish_realtime(
		EVENT_INVITE_ANSWER,
		{"guest": entry["name"], "accepted": accepted, "area_title": invite["area_title"]},
		user=invite["by"],
	)
	return _invite_for_guest(guest_id) if accepted else None


def _check_arrival(guest_id, x, y):
	"""Arrived in the customer meeting area: the corridor closes. Walked out again after arriving:
	the invite is over, so the guest cannot come back later into someone else's meeting."""
	invite = _invite(guest_id)
	if not invite or invite["status"] not in ("accepted", "arrived"):
		return
	room = next((a for a in ophice._areas() if a.name == invite["area"]), None)
	inside = bool(room and _inside(room, x, y))
	if invite["status"] == "accepted" and inside:
		invite["status"] = "arrived"
		invite.pop("corridor", None)
		frappe.cache.hset(INVITE_CACHE_KEY, guest_id, invite)
	elif invite["status"] == "arrived" and not inside:
		frappe.cache.hdel(INVITE_CACHE_KEY, guest_id)
