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


# --- Session


def _sign(guest_id):
	from frappe.utils.password import get_encryption_key

	return hmac.new(get_encryption_key().encode(), guest_id.encode(), hashlib.sha256).hexdigest()[:32]


def _token(guest_id):
	return f"{guest_id}.{_sign(guest_id)}"


def _sessions():
	"""Live guest sessions {guest_id: entry}; expired ones are dropped on the way."""
	now = time.time()
	live = {}
	for guest_id, entry in (frappe.cache.hgetall(GUEST_CACHE_KEY) or {}).items():
		guest_id = frappe.safe_decode(guest_id)
		if not isinstance(entry, dict) or entry.get("expires", 0) < now:
			frappe.cache.hdel(GUEST_CACHE_KEY, guest_id)
			frappe.cache.hdel(ophice.PRESENCE_CACHE_KEY, GUEST_PREFIX + guest_id)
			continue
		live[guest_id] = entry
	return live


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
	if not isinstance(entry, dict) or entry.get("expires", 0) < time.time():
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
	"""The areas this guest may stand in: the guest area (invites add more, #2084)."""
	area = guest_area()
	return [area] if area else []


def _inside(area, x, y):
	cx, cy = x + 0.5, y + 0.5
	return area.x <= cx <= area.x + area.width and area.y <= cy <= area.y + area.height


def clamp_to(areas, x, y):
	"""The nearest position whose chip centre lies inside one of the areas."""
	best = None
	for area in areas:
		cx = min(max(float(x) + 0.5, area.x), area.x + area.width)
		cy = min(max(float(y) + 0.5, area.y), area.y + area.height)
		distance = (cx - x - 0.5) ** 2 + (cy - y - 0.5) ** 2
		if best is None or distance < best[0]:
			best = (distance, round(cx - 0.5, 2), round(cy - 0.5, 2))
	return (best[1], best[2]) if best else (float(x), float(y))


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
		points = [(float(p[0]), float(p[1])) for p in samples]
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
	if len(_sessions()) >= MAX_GUESTS:
		frappe.throw(_("Ophice is full right now. Please try again in a few minutes."))
	guest_id = frappe.generate_hash(length=20)
	entry = {
		"name": name,
		"expires": time.time() + SESSION_SECONDS,
		"ip": getattr(frappe.local, "request_ip", "") or "",
	}
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
	me = frappe.cache.hget(ophice.PRESENCE_CACHE_KEY, GUEST_PREFIX + guest_id)
	if isinstance(me, dict):
		x, y = clamp_to(areas, me["x"], me["y"])
	else:
		spot = ophice._free_spot(areas[0], GUEST_PREFIX + guest_id) if areas else ophice._spawn()
		x, y = spot["x"], spot["y"]
	chip = _put(guest_id, entry, x, y, publish_event=None if isinstance(me, dict) else ophice.EVENT_PRESENCE)
	# Only chips inside my areas: nothing about anyone elsewhere in the office.
	others = [
		{k: c.get(k) for k in ("user", "full_name", "user_image", "x", "y", "guest")}
		for c in ophice._online(exclude=chip["user"])
		if any(_inside(a, c["x"], c["y"]) for a in areas)
	]
	background = ophice._background()
	return {
		"cols": ophice.COLS,
		"rows": ophice.ROWS,
		"me": chip,
		"areas": [_rect(a) for a in areas],
		"others": others,
		"background": background.get("url") or "",
		"background_layout": ophice._background_layout(background),
		"expires_in": max(0, round(entry["expires"] - time.time())),
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def guest_move(x, y):
	"""I walked: the position is kept inside my areas and shown to the employees."""
	guest_id, entry = _require_guest()
	if _throttled(guest_id):
		return None
	x, y = clamp_to(allowed_areas(guest_id), frappe.utils.flt(x), frappe.utils.flt(y))
	_put(guest_id, entry, x, y, publish_event=ophice.EVENT_MOVE)
	return {"x": x, "y": y}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def guest_leave():
	"""I closed the page: the visit ends, my chip disappears."""
	guest_id, _entry = _current_guest()
	if not guest_id:
		return False
	frappe.cache.hdel(GUEST_CACHE_KEY, guest_id)
	frappe.cache.hdel(ophice.PRESENCE_CACHE_KEY, GUEST_PREFIX + guest_id)
	ophice._publish(ophice.EVENT_LEAVE, {"user": GUEST_PREFIX + guest_id})
	_set_cookie("", 1)
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
