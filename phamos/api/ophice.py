# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Ophice (#2053): colleagues as avatar chips on a grid.

Slice 1 (#2054) keeps the user's own chip: where it stands, saved as a user default so it is
back in the same spot after a reload, in any browser. No DocType, nothing to migrate.

Positions are in tile units but not whole tiles: the grid is drawn, movement is free.

Slice 2 (#2055), presence: who has the page open lives in the Redis cache only (a hash
user → position and last heartbeat), never in the database, and no history is kept. A heartbeat
every few seconds keeps a user online; without one for PRESENCE_TTL seconds, or after leave(),
the chip is gone. Joins, moves and leaves go out over Frappe realtime to the site room, which
only System Users join, so only System Users may use Ophice.

Dummy chips for testing come from the site config, so they never appear on a site that does
not set them:

	"ophice_dummies": [{"user": "chip-buddy@example.com", "x": 24, "y": 12}]
"""

import hashlib
import html
import json
import math
import random
import re
import time
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import add_to_date, escape_html, get_datetime, now_datetime, strip_html

from phamos.cockpits.settings import COCKPITS as _COCKPITS

# One shared world for everyone; the frontend draws exactly this grid.
# The walkable grid (#2089): a site value map editors can grow; these are the defaults.
COLS = 40
ROWS = 25
GRID_KEY = "phamos_ophice_grid"
GRID_LIMITS = ((10, 120), (10, 80))
EVENT_GRID = "ophice_grid"
POSITION_KEY = "phamos_ophice_position"
DUMMIES_CONF_KEY = "ophice_dummies"
MAX_DUMMIES = 10

PRESENCE_CACHE_KEY = "phamos_ophice_presence"
# Seconds without a heartbeat after which a chip counts as gone (the page beats every 10 s).
PRESENCE_TTL = 45
# Moves per user: at most this many in MOVE_WINDOW seconds (the page sends about 8 a second).
MOVE_LIMIT = 60
MOVE_WINDOW = 5

EVENT_PRESENCE = "ophice_presence"
EVENT_MOVE = "ophice_move"
EVENT_LEAVE = "ophice_leave"
EVENT_MESSAGE = "ophice_message"
# The other person's page opens the chat too when one of the two starts it (#2056).
EVENT_STARTED = "ophice_encounter_started"
EVENT_BACKGROUND = "ophice_background"

# Ophice's background image: one for everyone, any Ophice user may change it (PM, 2026-11-21).
# Stored as a global default {"url", "file"}; the previous image's File is deleted on change.
BACKGROUND_KEY = "phamos_ophice_background"
BACKGROUND_MAX_BYTES = 5 * 1024 * 1024
# Checked by opening the image, not by the file name: no SVG (scripts), no disguised files.
BACKGROUND_FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif"}

# Encounters (#2056): two chips closer than ENCOUNTER_DISTANCE (centres, in tiles) meet. The
# server allows some slack, since positions it knows may be a few hundred ms old.
ENCOUNTER_DISTANCE = 2.0  # the pages draw a perimeter of radius 1 tile around every chip
SERVER_DISTANCE_SLACK = 1.5
ENCOUNTER_DOCTYPE = "Ophice Encounter"
MAX_MESSAGE_LENGTH = 2000
MESSAGES_SHOWN = 100

# Burn notice (#2057): after parting, the chat burns this many seconds later unless both save it.
BURN_SECONDS = 60
EVENT_BURN_NOTICE = "ophice_burn_notice"
EVENT_BURN_CANCEL = "ophice_burn_cancel"
EVENT_SAVE_VOTE = "ophice_save_vote"
EVENT_SAVED = "ophice_saved"
EVENT_BURNED = "ophice_burned"

# Video call on encounter (#2059): a Jitsi room per encounter, joined muted with the camera off.
# Site config: "ophice_jitsi_domain" (default meet.jit.si), "ophice_video": 0 turns it off.
JITSI_DEFAULT_DOMAIN = "meet.jit.si"

# Meeting areas (#2060): rectangles of the grid with a fixed Jitsi meeting.
AREA_DOCTYPE = "Ophice Area"
EVENT_AREAS = "ophice_areas"
MAX_AREAS = 50
# Every area gets its own random color (PM, 2026-11-22): a hue, at least this far from the others.
AREA_HUE_GAP = 30
AREA_TITLE_LENGTH = 60
# The app icon colours of the cockpits (phamos/cockpits/settings.py), for cockpit spaces (#2076).
COCKPIT_COLORS = {route: color for route, (_prefix, color) in _COCKPITS.items()}
# Areas are drawn in half tiles (#2067).
AREA_STEP = 0.5
# Kinds of space (#2072): a meeting, or the start space where chips are beamed in.
AREA_KINDS = ("Meeting", "Start", "Guest", "Customer meeting", "Cockpit", "Phriend")
# Kinds with a meeting: whoever stops inside joins it (#2060, #2081). Guest and Customer meeting
# are also where external guests may be (#2080).
MEETING_KINDS = ("Meeting", "Guest", "Customer meeting", "Cockpit")
# Spaces whose meeting has the normal area chat (Raven batches); guest kinds have the guest chat.
AREA_CHAT_KINDS = ("Meeting", "Cockpit")
# Only one of each of these on the map.
SINGLE_KINDS = ("Start", "Guest", "Phriend")
# Coming in (#2072): first visit of the day, or back after this long. Last visit per user in Redis.
ARRIVAL_GAP_SECONDS = 5 * 60
LAST_SEEN_CACHE_KEY = "phamos_ophice_last_seen"
# Chips in the start space keep at least this distance (tiles) from each other.
START_SPOT_GAP = 1.2
# Area chat (#2062): what happens to what is written in an area.
CHAT_MODES = ("Saved", "Not saved", "Confidential")
EVENT_AREA_MESSAGE = "ophice_area_message"
EVENT_AREA_BATCHES = "ophice_area_batches"
# Chat batches (#2066): one per meeting; grace time after the area empties, then a Keep/Burn vote.
BATCH_DOCTYPE = "Ophice Chat Batch"
BATCH_GRACE_MINUTES = 10
BATCH_VOTE_HOURS = 24
BATCHES_SHOWN = 20
# People list (#2063): everyone sees who is around; each user can hide their details.
HIDE_KEY = "phamos_ophice_hide_details"
# Cockpit spaces (#2076): stopping inside opens the cockpit, unless switched off (per user).
AUTO_COCKPIT_KEY = "phamos_ophice_no_auto_cockpit"
RECENT_CHATS = 5
# Which cockpit someone is in (#2065): a heartbeat from every cockpit tab while it is visible.
COCKPIT_CACHE_KEY = "phamos_ophice_cockpits"
COCKPIT_TTL = 75
# The server sees moves a moment late: a chip this close to the edge still counts as inside.
AREA_SLACK = 0.5

# Status (#2053): "Be right back" or "Away" with a note and a return time, shown above the chip.
STATUS_KEY = "phamos_ophice_status"
EVENT_STATUS = "ophice_status"
STATUS_KINDS = ("brb", "away")
# "Be right back" with a return time, at most this far ahead (#2074).
BRB_MAX_HOURS = 24
STATUS_NOTE_LENGTH = 140
AWAY_MAX_DAYS = 14
# An away chip stays on the map (offline) until this long after its return time.
AWAY_GRACE_SECONDS = 3600


def check_app_permission():
	"""Ophice on the Apps screen (#2070): for the people who may use it, every System User, as
	when it was a page of the Personal Cockpit."""
	if frappe.session.user == "Guest":
		return False
	return frappe.get_cached_value("User", frappe.session.user, "user_type") == "System User"


# Who may change the map (#2071): spaces and the background. Everyone else only uses it.
MAP_EDITOR_ROLE = "Ophice Map Editor"


def can_edit_map(user=None):
	user = user or frappe.session.user
	return user == "Administrator" or MAP_EDITOR_ROLE in frappe.get_roles(user)


def _start_page_on():
	return bool(frappe.db.get_single_value("Cockpit Settings", "ophice_start_page"))


def check_start_tile_permission():
	"""Ophice's first Apps-screen tile: only while it is the start page (#2077)."""
	return check_app_permission() and _start_page_on()


def check_tile_permission():
	"""Ophice's other Apps-screen tile: while it is not the start page."""
	return check_app_permission() and not _start_page_on()


def _require_map_editor():
	_require_user()
	if not can_edit_map():
		frappe.throw(_("Only Ophice map editors can change the map."), frappe.PermissionError)


def _require_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to use Ophice."), frappe.PermissionError)
	# Realtime events reach System Users only (the site room), so nobody else could see anyone.
	if frappe.get_cached_value("User", frappe.session.user, "user_type") != "System User":
		frappe.throw(_("Ophice is only available to System Users."), frappe.PermissionError)


def _grid():
	"""(cols, rows) of the walkable grid: the stored size, else 40 x 25 (#2089)."""
	# Read from the table, not frappe.db.get_default(): its Redis cache survives test rollbacks.
	raw = frappe.db.get_value("DefaultValue", {"parent": "__default", "defkey": GRID_KEY}, "defvalue")
	try:
		data = json.loads(raw or "{}")
	except (TypeError, ValueError):
		data = {}
	if not isinstance(data, dict):
		data = {}
	(cmin, cmax), (rmin, rmax) = GRID_LIMITS
	cols = max(cmin, min(cmax, frappe.utils.cint(data.get("cols")) or COLS))
	rows = max(rmin, min(rmax, frappe.utils.cint(data.get("rows")) or ROWS))
	return cols, rows


def _cols():
	return _request_grid()[0]


def _rows():
	return _request_grid()[1]


def _request_grid():
	"""The grid size, read once per request: move and heartbeat (several a second per walking
	user) would otherwise read it from the database twice on every call."""
	# Only inside a web request: frappe.local lives as long as the request there. Elsewhere (jobs,
	# tests) it can outlive a rollback, so the value is read fresh.
	request = getattr(frappe.local, "request", None)
	if request is None:
		return _grid()
	cached = getattr(frappe.local, "ophice_grid", None)
	if cached is None or cached[0] is not request:
		cached = frappe.local.ophice_grid = (request, _grid())
	return cached[1]


@frappe.whitelist(methods=["POST"])
def set_grid(cols, rows):
	"""Grow or shrink the walkable grid, for everyone (map editors only, #2089). Shrinking is
	refused while a space would end up outside; chips are moved onto the grid as they arrive."""
	_require_map_editor()
	(cmin, cmax), (rmin, rmax) = GRID_LIMITS
	cols = max(cmin, min(cmax, frappe.utils.cint(cols)))
	rows = max(rmin, min(rmax, frappe.utils.cint(rows)))
	for area in _areas():
		if area.x + area.width > cols + 1e-9 or area.y + area.height > rows + 1e-9:
			frappe.throw(
				_("The space {0} would be cut off. Move or shrink it first.").format(area.title),
				title=_("Grid too small"),
			)
	frappe.db.set_default(GRID_KEY, json.dumps({"cols": cols, "rows": rows}, separators=(",", ":")))
	frappe.local.ophice_grid = None
	_publish(EVENT_GRID, {"cols": cols, "rows": rows, "by": frappe.session.user})
	return {"cols": cols, "rows": rows}


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
	return {"x": float(_cols() // 2), "y": float(_rows() // 2)}


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
	return {"x": _clamp(data.get("x"), _cols()), "y": _clamp(data.get("y"), _rows())}


def _chip(user, position):
	full_name, user_image = frappe.db.get_value("User", user, ["full_name", "user_image"]) or ("", "")
	return {
		**position,
		"user": user,
		"full_name": full_name or user,
		"user_image": user_image or "",
		"status": _status_of(user),
	}


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
		chips.append(_chip(user, {"x": _clamp(entry.get("x"), _cols()), "y": _clamp(entry.get("y"), _rows()), "dummy": True}))
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
	key = frappe.cache.make_key(f"phamos_ophice_moves:{frappe.session.user}")
	count = frappe.cache.incrby(key, 1)
	if count == 1:
		frappe.cache.expire(key, MOVE_WINDOW)
	return count > MOVE_LIMIT


# --- Coming in (#2072): the chip is beamed in at the start space.


def _last_seen(user):
	try:
		return float(frappe.cache.hget(LAST_SEEN_CACHE_KEY, user) or 0)
	except (TypeError, ValueError):
		return 0.0


def _touch(user):
	frappe.cache.hset(LAST_SEEN_CACHE_KEY, user, time.time())


def _arriving(user):
	"""First visit of the day, or back after more than ARRIVAL_GAP_SECONDS: a reload or a short
	connection loss is not an arrival, so nobody drops out of a meeting."""
	seen = _last_seen(user)
	if not seen or time.time() - seen > ARRIVAL_GAP_SECONDS:
		return True
	zone = ZoneInfo(frappe.utils.get_system_timezone())
	return datetime.fromtimestamp(seen, zone).date() != datetime.now(zone).date()


def _start_space():
	return next((a for a in _areas() if a.kind == "Start"), None)


def _start_spot(user):
	"""A free spot in the start space (not on top of anyone), or the middle of the map without one."""
	start = _start_space()
	if not start:
		return _spawn()
	return _free_spot(start, user)


def _free_spot(start, user):
	"""A free spot inside an area (not on top of anyone), or its middle when it is full (#2072, #2082)."""
	taken = [(c["x"], c["y"]) for c in _online(exclude=user)]
	spots = []
	y = start.y
	while y + 1 <= start.y + start.height + 1e-9:
		x = start.x
		while x + 1 <= start.x + start.width + 1e-9:
			if all(math.hypot(x - tx, y - ty) >= START_SPOT_GAP for tx, ty in taken):
				spots.append({"x": float(x), "y": float(y)})
			x += 1
		y += 1
	if spots:
		return random.choice(spots)
	# Too small or full: the middle of it (chips are drawn one tile wide).
	return {
		"x": _clamp(start.x + start.width / 2 - 0.5, _cols()),
		"y": _clamp(start.y + start.height / 2 - 0.5, _rows()),
	}


def _beam_key(user):
	return f"phamos_ophice_beam:{user}"


@frappe.whitelist()
def get_space():
	"""The grid size, my chip (where it stands, or the spawn) and the other chips."""
	_require_user()
	user = frappe.session.user
	dummies = _dummies(user)
	dummy_users = {d["user"] for d in dummies}
	online = [c for c in _online(exclude=user) if c["user"] not in dummy_users]
	present = dummy_users | {c["user"] for c in online} | {user}
	arriving = _arriving(user)
	if arriving:
		# Beamed in at the start space; the others see it with my first heartbeat.
		position = _start_spot(user)
		frappe.defaults.set_user_default(POSITION_KEY, json.dumps(position, separators=(",", ":")))
		frappe.cache.set_value(_beam_key(user), 1, expires_in_sec=60)
	else:
		position = _stored_position() or _spawn()
	_touch(user)
	return {
		"cols": _cols(),
		"rows": _rows(),
		"me": {**_chip(user, position), "cols": _cols(), "rows": _rows()},
		"beam_in": arriving,
		"others": dummies + online + [c for c in _away_offline() if c["user"] not in present],
		"presence_ttl": PRESENCE_TTL,
		# Burn notices still running for me (#2057), e.g. after a reload.
		"notices": _my_notices(user),
		"background": _background().get("url") or "",
		"background_layout": _background_layout(_background()),
		"background_ratio": _background_ratio(_background()),
		"areas": _areas(),
		# The map tools and the Debug menu are only shown to map editors (#2071).
		"can_edit_map": can_edit_map(user),
		# Cockpit spaces open their cockpit when I stop inside (#2076), unless I switched it off.
		"auto_cockpit": _auto_cockpit(user),
	}


@frappe.whitelist(methods=["POST"])
def heartbeat(x, y):
	"""I am here (join, and every few seconds while the page is open), standing at x, y."""
	_require_user()
	user = frappe.session.user
	chip = _chip(user, {"x": _clamp(x, _cols()), "y": _clamp(y, _rows())})
	frappe.cache.hset(PRESENCE_CACHE_KEY, user, {**chip, "ts": time.time()})
	_touch(user)
	# Just came in (#2072): the others play the beam-in once.
	beam = bool(frappe.cache.get_value(_beam_key(user)))
	if beam:
		frappe.cache.delete_value(_beam_key(user))
	_publish(EVENT_PRESENCE, {**chip, "beam": True} if beam else chip)
	return chip


@frappe.whitelist(methods=["POST"])
def move(x, y, lift=0):
	"""Tell the others where my chip is now. Only for a chip that is present (heartbeat first).

	`lift`: the chip was lifted out of a meeting space (Leave or Esc), the others see it carried.
	"""
	_require_user()
	user = frappe.session.user
	entry = frappe.cache.hget(PRESENCE_CACHE_KEY, user)
	if not isinstance(entry, dict) or _throttled():
		return None
	entry.update({"x": _clamp(x, _cols()), "y": _clamp(y, _rows()), "ts": time.time()})
	frappe.cache.hset(PRESENCE_CACHE_KEY, user, entry)
	message = {"user": user, "x": entry["x"], "y": entry["y"]}
	if frappe.utils.cint(lift):
		message["lift"] = 1
	_publish(EVENT_MOVE, message)
	return message


@frappe.whitelist(methods=["POST"])
def leave():
	"""I closed the page: my chip disappears for everyone right away."""
	_require_user()
	user = frappe.session.user
	frappe.cache.hdel(PRESENCE_CACHE_KEY, user)
	status = _status_of(user)
	if status and status["kind"] == "away":
		# Away chips stay on the map, greyed out, so the others see when I am back.
		_publish(EVENT_PRESENCE, {**_chip(user, _stored_position() or _spawn()), "offline": True})
	else:
		_publish(EVENT_LEAVE, {"user": user})
	# Leaving the page is parting from everyone I was chatting with (#2057).
	_part_all_mine(user)


@frappe.whitelist(methods=["POST"])
def save_my_position(x, y):
	"""Remember where my chip stands; values outside the grid are moved onto its edge."""
	_require_user()
	position = {"x": _clamp(x, _cols()), "y": _clamp(y, _rows())}
	frappe.defaults.set_user_default(POSITION_KEY, json.dumps(position, separators=(",", ":")))
	return position


# --- Status (#2053): "Be right back" and "Away", with a note and a return time.
#
# Stored per user as a user default (JSON). The return time is an instant in UTC ("...Z");
# each page shows it in the viewer's own time zone. "tz" is the IANA zone of whoever set it,
# so others can also see the time on their clock.


def _utc(value):
	return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_instant(value):
	"""An ISO 8601 time with a zone (from the browser: Date.toISOString()) as an aware datetime."""
	if not isinstance(value, str) or not value.strip():
		return None
	try:
		parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
	except ValueError:
		return None
	# A time without a zone is ambiguous across time zones: refuse it.
	return parsed if parsed.tzinfo else None


def _clean_status(data):
	"""A stored status, or None when it is empty, broken or an away that is long over."""
	if not isinstance(data, dict) or data.get("kind") not in STATUS_KINDS:
		return None
	status = {
		"kind": data["kind"],
		"note": str(data.get("note") or "")[:STATUS_NOTE_LENGTH],
		"until": "",
		"tz": str(data.get("tz") or ""),
		"since": str(data.get("since") or ""),
	}
	if status["kind"] == "away":
		until = _parse_instant(data.get("until"))
		if not until:
			return None
		if until + timedelta(seconds=AWAY_GRACE_SECONDS) < datetime.now(timezone.utc):
			return None
		status["until"] = _utc(until)
	elif data.get("until"):
		# "Be right back" may say when (#2074: "I'll get back to you in 15 min"), counting down.
		until = _parse_instant(data.get("until"))
		if until:
			status["until"] = _utc(until)
	return status


def _status_of(user):
	# Straight from the table: the defaults' Redis cache can outlive a test rollback.
	raw = frappe.db.get_value("DefaultValue", {"parent": user, "defkey": STATUS_KEY}, "defvalue")
	if not raw:
		return None
	try:
		return _clean_status(json.loads(raw))
	except (TypeError, ValueError):
		return None


def _valid_zone(name):
	if not isinstance(name, str) or not name or len(name) > 64:
		return ""
	try:
		ZoneInfo(name)
	except Exception:
		return ""
	return name


@frappe.whitelist(methods=["POST"])
def set_status(kind="", note="", until="", tz=""):
	"""Set my status ("brb" or "away"), or clear it (empty kind). Away needs a return time."""
	_require_user()
	user = frappe.session.user
	kind = (kind or "").strip()
	if not kind:
		frappe.defaults.clear_user_default(STATUS_KEY, user)
		status = None
	else:
		if kind not in STATUS_KINDS:
			frappe.throw(_("Unknown status."))
		note = strip_html(note or "").strip()
		if len(note) > STATUS_NOTE_LENGTH:
			frappe.throw(_("The note can be at most {0} characters.").format(STATUS_NOTE_LENGTH))
		now = datetime.now(timezone.utc)
		status = {"kind": kind, "note": note, "until": "", "tz": _valid_zone(tz), "since": _utc(now)}
		if kind == "away":
			back = _parse_instant(until)
			if not back:
				frappe.throw(_("Please say when you will be back."))
			if back <= now:
				frappe.throw(_("The return time must be in the future."))
			if back > now + timedelta(days=AWAY_MAX_DAYS):
				frappe.throw(_("The return time can be at most {0} days ahead.").format(AWAY_MAX_DAYS))
			status["until"] = _utc(back)
		elif until:
			# "Be right back" with a time (#2074): in the future, within a day.
			back = _parse_instant(until)
			if not back or back <= now:
				frappe.throw(_("The return time must be in the future."))
			if back > now + timedelta(hours=BRB_MAX_HOURS):
				frappe.throw(_("For more than {0} hours, please set Away.").format(BRB_MAX_HOURS))
			status["until"] = _utc(back)
		frappe.defaults.set_user_default(STATUS_KEY, json.dumps(status, separators=(",", ":")), user)
	entry = frappe.cache.hget(PRESENCE_CACHE_KEY, user)
	if isinstance(entry, dict):
		entry["status"] = status
		frappe.cache.hset(PRESENCE_CACHE_KEY, user, entry)
	_publish(EVENT_STATUS, {"user": user, "status": status})
	return status


def _away_offline():
	"""Chips of users who are away and closed the page: shown greyed out until they are back."""
	rows = frappe.db.get_all(
		"DefaultValue",
		filters={"defkey": STATUS_KEY, "parent": ["not like", "\\_\\_%"]},
		fields=["parent", "defvalue"],
	)
	chips = []
	for row in rows:
		try:
			status = _clean_status(json.loads(row.defvalue or ""))
		except (TypeError, ValueError):
			continue
		if not status or status["kind"] != "away":
			continue
		enabled, user_type = frappe.db.get_value("User", row.parent, ["enabled", "user_type"]) or (0, "")
		if not enabled or user_type != "System User":
			continue
		raw = frappe.db.get_value("DefaultValue", {"parent": row.parent, "defkey": POSITION_KEY}, "defvalue")
		try:
			data = json.loads(raw) if raw else None
		except (TypeError, ValueError):
			data = None
		if not isinstance(data, dict):
			continue
		position = {"x": _clamp(data.get("x"), _cols()), "y": _clamp(data.get("y"), _rows()), "offline": True}
		chips.append(_chip(row.parent, position))
	return chips


# --- Background image of Ophice (shared).


def _background():
	# Read from the table, not frappe.db.get_default(): its Redis cache survives a rollback and
	# could show a background whose File was never committed.
	raw = frappe.db.get_value("DefaultValue", {"parent": "__default", "defkey": BACKGROUND_KEY}, "defvalue")
	try:
		value = json.loads(raw or "{}")
	except (TypeError, ValueError):
		value = {}
	return value if isinstance(value, dict) else {}


# How the image lies on the map (#2089): "fit" (covers the grid), or a place and width in grid
# tiles; the height follows the image's ratio. It may reach beyond the grid: those parts are
# shown dimmed. "zoom" is everyone's starting zoom (1 = the whole grid fits the window).
BACKGROUND_MIN_WIDTH = 5
ZOOM_RANGE = (1.0, 3.0)


def _background_ratio(value):
	"""Width / height of the background image: stored at upload, else read once from the file."""
	ratio = frappe.utils.flt(value.get("ratio"))
	if ratio > 0:
		return ratio
	if not value.get("file") or not frappe.db.exists("File", value["file"]):
		return None
	from PIL import Image

	try:
		path = frappe.get_doc("File", value["file"]).get_full_path()
		with Image.open(path) as image:
			width, height = image.size
	except Exception:
		return None
	return round(width / height, 6) if height else None


def _background_layout(value):
	layout = value.get("layout") if isinstance(value.get("layout"), dict) else {}
	cols, rows = _grid()
	zoom = round(max(ZOOM_RANGE[0], min(ZOOM_RANGE[1], frappe.utils.flt(layout.get("zoom")) or 1)), 2)
	if layout.get("fit", True):
		return {"fit": True, "left": 0, "top": 0, "width": cols, "zoom": zoom}
	ratio = _background_ratio(value) or cols / rows
	if "width" not in layout:
		# The first layout (#2058): size in % of the grid width, CSS background-position in %.
		width = frappe.utils.flt(layout.get("scale") or 100) / 100 * cols
		height = width / ratio
		left = (cols - width) * frappe.utils.flt(layout.get("x", 50)) / 100
		top = (rows - height) * frappe.utils.flt(layout.get("y", 50)) / 100
	else:
		width = frappe.utils.flt(layout.get("width")) or cols
		left = frappe.utils.flt(layout.get("left"))
		top = frappe.utils.flt(layout.get("top"))
	width = max(BACKGROUND_MIN_WIDTH, min(4 * cols, width))
	height = width / ratio
	left = max(-width, min(cols, left))
	top = max(-height, min(rows, top))
	return {"fit": False, "left": round(left, 3), "top": round(top, 3), "width": round(width, 3), "zoom": zoom}


@frappe.whitelist(methods=["POST"])
def set_background_layout(fit=1, left=0, top=0, width=None, zoom=1):
	"""Place and size of the background image on the map, and the starting zoom, for everyone."""
	_require_map_editor()
	value = _background()
	if not value.get("url"):
		frappe.throw(_("Upload a background first."))
	value["layout"] = {
		"fit": bool(frappe.utils.cint(fit)),
		"left": frappe.utils.flt(left),
		"top": frappe.utils.flt(top),
		"width": frappe.utils.flt(width) or _cols(),
		"zoom": frappe.utils.flt(zoom) or 1,
	}
	layout = _background_layout(value)
	value["layout"] = layout
	frappe.db.set_default(BACKGROUND_KEY, json.dumps(value, separators=(",", ":")))
	_publish(EVENT_BACKGROUND, {"url": value["url"], "layout": layout, "ratio": _background_ratio(value), "by": frappe.session.user})
	return layout


def _set_background(value):
	previous = _background().get("file")
	frappe.db.set_default(BACKGROUND_KEY, json.dumps(value, separators=(",", ":")) if value else "")
	if previous and previous != value.get("file") and frappe.db.exists("File", previous):
		frappe.delete_doc("File", previous, ignore_permissions=True, delete_permanently=True)
	# A new image starts fitted to the grid.
	_publish(
		EVENT_BACKGROUND,
		{
			"url": value.get("url", ""),
			"layout": _background_layout(value),
			"ratio": _background_ratio(value) if value else None,
			"by": frappe.session.user,
		},
	)


def _store_background(content, filename):
	"""Check that the bytes are a real image of an allowed format, save them as a public File and
	make it the background. Returns the URL."""
	from io import BytesIO

	from PIL import Image, UnidentifiedImageError

	if not content:
		frappe.throw(_("Choose an image first."))
	if len(content) > BACKGROUND_MAX_BYTES:
		frappe.throw(_("The image can be at most {0} MB.").format(BACKGROUND_MAX_BYTES // (1024 * 1024)))
	try:
		with Image.open(BytesIO(content)) as image:
			image_format = image.format
			width, height = image.size
			image.verify()
	except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
		frappe.throw(_("This file is not an image Ophice can show (PNG, JPEG, WebP or GIF)."))
	extension = BACKGROUND_FORMATS.get(image_format)
	if not extension:
		frappe.throw(_("This file is not an image Ophice can show (PNG, JPEG, WebP or GIF)."))
	stem = re.sub(r"[^A-Za-z0-9_-]+", "-", (filename or "").rsplit(".", 1)[0]).strip("-")[:60] or "background"
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"ophice-{stem}.{extension}",
			"content": content,
			# Public: every Ophice user loads it as a CSS background (see "Verify before production").
			"is_private": 0,
			"folder": "Home",
		}
	).insert(ignore_permissions=True)
	# The ratio places the image in grid tiles (#2089).
	_set_background({"url": file_doc.file_url, "file": file_doc.name, "ratio": round(width / height, 6) if height else None})
	return file_doc.file_url


@frappe.whitelist(methods=["POST"])
def upload_background():
	"""Upload an image (multipart field "file") as Ophice's background, for everyone."""
	_require_map_editor()
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(_("Choose an image first."))
	# One byte more than allowed is enough to know it is too big.
	content = upload.stream.read(BACKGROUND_MAX_BYTES + 1)
	return {"url": _store_background(content, upload.filename)}


@frappe.whitelist(methods=["POST"])
def remove_background():
	"""Back to the plain grid, for everyone."""
	_require_map_editor()
	_set_background({})


# --- Encounters (#2056): a temporary private Raven channel for two chips that meet.


def _position_of(user):
	"""Where the server last saw a user's chip: presence first, then a dummy from the site config."""
	entry = frappe.cache.hget(PRESENCE_CACHE_KEY, user)
	if isinstance(entry, dict) and time.time() - entry.get("ts", 0) <= PRESENCE_TTL:
		return entry["x"], entry["y"]
	for dummy in _dummies(None):
		if dummy["user"] == user:
			return dummy["x"], dummy["y"]
	return None


PAIR_LOCK_SECONDS = 10


def _lock_pair(pair_key):
	"""MariaDB GET_LOCK for this pair, released when this request commits or rolls back."""
	# Lock names are at most 64 characters.
	name = "phamos_ophice_" + hashlib.md5(pair_key.encode()).hexdigest()
	got = frappe.db.sql("SELECT GET_LOCK(%s, %s)", (name, PAIR_LOCK_SECONDS))[0][0]
	if not got:
		frappe.throw(_("The chat is just being opened. Please try again."))

	def release():
		frappe.db.sql("SELECT RELEASE_LOCK(%s)", (name,))

	frappe.db.after_commit.add(release)
	frappe.db.after_rollback.add(release)


def _pair_key(user_a, user_b):
	return "|".join(sorted((user_a, user_b)))


def _open_encounter_name(pair_key, for_update=False):
	# Open or Parting: the record exists only until it is saved or burned. `for_update` is a
	# locking read: it sees a row another request committed after this transaction began.
	return frappe.db.get_value(ENCOUNTER_DOCTYPE, {"pair_key": pair_key}, "name", for_update=for_update)


ENCOUNTER_FIELDS = [
	"name", "user_a", "user_b", "status", "raven_channel", "jitsi_room", "burn_at", "saved_by_a", "saved_by_b"
]


def _require_party(encounter, statuses=("Open",), for_update=False):
	"""The encounter, if the session user is one of its two people and it is in one of `statuses`.

	A saved or burned encounter no longer exists: "This chat has ended." `for_update` reads the
	latest committed row (see open_encounter).
	"""
	doc = frappe.db.get_value(ENCOUNTER_DOCTYPE, encounter, ENCOUNTER_FIELDS, as_dict=True, for_update=for_update)
	if not doc:
		frappe.throw(_("This chat has ended."))
	if frappe.session.user not in (doc.user_a, doc.user_b):
		frappe.throw(_("This chat is not yours."), frappe.PermissionError)
	if doc.status not in statuses:
		frappe.throw(_("This chat has ended."))
	return doc


def _peer(doc):
	return doc.user_b if frappe.session.user == doc.user_a else doc.user_a


def _create_channel(user_a, user_b):
	from phamos.api.issue_chat import _ensure_members, _resolve_workspace

	channel = frappe.get_doc(
		{
			"doctype": "Raven Channel",
			# Raven needs a unique, readable name; the time keeps re-meetings apart.
			"channel_name": f"encounter-{frappe.generate_hash(length=10)}",
			"channel_description": _("Ophice encounter, {0}").format(now_datetime().strftime("%Y-%m-%d %H:%M")),
			"type": "Private",
			"workspace": _resolve_workspace(),
		}
	)
	channel.flags.do_not_add_member = True
	channel.insert(ignore_permissions=True)
	skipped = _ensure_members(channel, [user_a, user_b], admin=user_a, silent=True)
	if skipped:
		frappe.throw(
			_("{0} can't chat: no Raven access.").format(
				", ".join(frappe.utils.get_fullname(u) for u in skipped)
			)
		)
	return channel.name


def _plain_text(markup):
	"""Raven's HTML as the text the person typed: line breaks kept, tags dropped, entities decoded."""
	text = re.sub(r"(?i)<br\s*/?>|</p>\s*<p[^>]*>", "\n", markup or "")
	return html.unescape(strip_html(text)).strip()


def _message_row(row):
	return {
		"name": row.name,
		"owner": row.owner,
		# Raven stores HTML; the bubble shows plain text (and Vue escapes it again).
		"text": _plain_text(row.text),
		"creation": str(row.creation),
	}


def _messages(channel):
	rows = frappe.get_all(
		"Raven Message",
		# Not "is_thread": in Raven that marks a message that *started* a thread; its replies live
		# in their own thread channel, so filtering by channel is enough.
		filters={"channel_id": channel, "message_type": ("!=", "System")},
		fields=["name", "owner", "text", "creation"],
		order_by="creation desc",
		limit=MESSAGES_SHOWN,
	)
	return [_message_row(r) for r in reversed(rows)]


def _video(doc):
	"""Where the two meet on video, or None when video is off for this site."""
	switch = frappe.conf.get("ophice_video")
	if switch is not None and not frappe.utils.cint(switch):
		return None
	domain = str(frappe.conf.get("ophice_jitsi_domain") or JITSI_DEFAULT_DOMAIN).strip().strip("/")
	# A bare host name: the page loads https://<domain>/external_api.js from it.
	if not re.fullmatch(r"[A-Za-z0-9.-]+(:\d+)?", domain):
		return None
	# From the row the caller read: open_encounter reads it fresh, so both pages get one room.
	room = doc.get("jitsi_room")
	if not room:
		# Encounters from before #2059 get their room on first use.
		room = _new_jitsi_room()
		frappe.db.set_value(ENCOUNTER_DOCTYPE, doc.name, "jitsi_room", room, update_modified=False)
	return {"domain": domain, "room": room}


def _new_jitsi_room():
	# Unguessable: on a public Jitsi server, whoever knows the name can walk in.
	return f"ophice-{frappe.generate_hash(length=24)}"


def _encounter_payload(doc):
	return {
		"video": _video(doc),
		"encounter": doc.name,
		"with": _peer(doc),
		"channel": doc.raven_channel,
		"messages": _messages(doc.raven_channel),
	}


@frappe.whitelist(methods=["POST"])
def open_encounter(with_user):
	"""Two chips met: get or start the encounter chat of the pair and return it with its messages.

	Both pages notice the meeting and both call this at the same moment. A database lock per
	pair, held until this request commits, lets them run one after the other: the second one
	finds the first one's encounter. (Racing inserts on the unique pair key deadlocked.)
	"""
	_require_user()
	me = frappe.session.user
	if not isinstance(with_user, str) or with_user == me or not frappe.db.get_value("User", with_user, "enabled"):
		frappe.throw(_("Nobody to chat with here."))
	mine, theirs = _position_of(me), _position_of(with_user)
	if not mine or not theirs or math.dist(mine, theirs) > ENCOUNTER_DISTANCE + SERVER_DISTANCE_SLACK:
		frappe.throw(_("Move closer to chat."))

	pair_key = _pair_key(me, with_user)
	_lock_pair(pair_key)
	# A locking read: it sees what the other request committed while this one waited.
	name = _open_encounter_name(pair_key, for_update=True)
	if name:
		# Met again while the burn notice ran: the chat goes on.
		_cancel_burn(_require_party(name, ("Open", "Parting"), for_update=True))
	else:
		user_a, user_b = sorted((me, with_user))
		doc = frappe.get_doc(
			{
				"doctype": ENCOUNTER_DOCTYPE,
				"user_a": user_a,
				"user_b": user_b,
				"status": "Open",
				"opened_at": now_datetime(),
				"pair_key": pair_key,
				"jitsi_room": _new_jitsi_room(),
			}
		)
		# The lock keeps the other page out; the unique index stays the last line of defence.
		frappe.db.savepoint("ophice_encounter")
		try:
			doc.insert(ignore_permissions=True)
		except (frappe.UniqueValidationError, frappe.DuplicateEntryError):
			frappe.db.rollback(save_point="ophice_encounter")
			# Frappe msgprints "Pair Key must be unique" before raising: drop it, or the page
			# shows an error although the chat opens fine.
			frappe.clear_last_message()
			name = _open_encounter_name(pair_key)
			if not name:
				frappe.throw(_("The chat is just being opened. Please try again."))
		else:
			doc.db_set("raven_channel", _create_channel(user_a, user_b), update_modified=False)
			name = doc.name
	# Locking read again: this transaction's snapshot may predate the other page's commit.
	payload = _encounter_payload(_require_party(name, for_update=True))
	# Chats start on a key press now (standing next to someone), not by walking past: tell the
	# other page, so its bubble opens without a key press there.
	frappe.publish_realtime(EVENT_STARTED, {"encounter": name, "with": me}, user=with_user, after_commit=True)
	return payload


@frappe.whitelist(methods=["POST"])
def send_encounter_message(encounter, text):
	"""Post a message into the encounter's Raven channel and tell both people right away."""
	_require_user()
	doc = _require_party(encounter)
	text = (text or "").strip()
	if not text:
		frappe.throw(_("Write something first."))
	if len(text) > MAX_MESSAGE_LENGTH:
		frappe.throw(_("A message can be at most {0} characters.").format(MAX_MESSAGE_LENGTH))
	# The party check above is the permission: the sender is a member of this private channel.
	message = frappe.get_doc(
		{
			"doctype": "Raven Message",
			"channel_id": doc.raven_channel,
			"message_type": "Text",
			"text": "<p>{}</p>".format(escape_html(text).replace("\n", "<br>")),
		}
	).insert(ignore_permissions=True)
	row = _message_row(message)
	payload = {"encounter": doc.name, "message": row}
	# Raven's own events differ between Raven 2 and 3; the bubble listens to this one only.
	for user in (doc.user_a, doc.user_b):
		frappe.publish_realtime(EVENT_MESSAGE, payload, user=user, after_commit=True)
	peer = _peer(doc)
	if peer in _dummy_users() and frappe.session.user not in _dummy_users():
		frappe.enqueue(
			"phamos.api.ophice.dummy_reply",
			queue="short",
			enqueue_after_commit=True,
			encounter=doc.name,
			dummy=peer,
		)
	return row


def _dummy_users():
	entries = frappe.conf.get(DUMMIES_CONF_KEY) or []
	return {e.get("user") for e in entries if isinstance(e, dict)} if isinstance(entries, list) else set()


DUMMY_REPLY_DELAY = 1.0


def dummy_reply(encounter, dummy):
	"""Background job: a test dummy (site config only) answers "Yes", "No" or "Maybe" at random."""
	if dummy not in _dummy_users():
		return
	time.sleep(DUMMY_REPLY_DELAY)  # a moment to "think", so it reads like a reply
	frappe.set_user(dummy)
	try:
		send_encounter_message(encounter, random.choice((_("Yes"), _("No"), _("Maybe"))))
	except frappe.ValidationError:
		# The encounter ended meanwhile.
		pass


# --- Burn notice, save, burn (#2057).
#
# Parting starts a countdown (status Parting, burn_at). Meeting again cancels it. When both press
# Save, the messages move into the two people's Raven DM; otherwise the channel and its messages
# are deleted for good when the countdown ends (the page asks at zero; burn_due_encounters runs
# every minute for closed tabs). Either way the encounter record itself is deleted.


def _saved_flags(doc, user):
	"""(I saved, they saved) from `user`'s point of view."""
	if user == doc.user_a:
		return bool(doc.saved_by_a), bool(doc.saved_by_b)
	return bool(doc.saved_by_b), bool(doc.saved_by_a)


def _notice_for(doc, user):
	peer = doc.user_b if user == doc.user_a else doc.user_a
	saved_me, saved_peer = _saved_flags(doc, user)
	full_name, user_image = frappe.db.get_value("User", peer, ["full_name", "user_image"]) or ("", "")
	return {
		"encounter": doc.name,
		"with": peer,
		"full_name": full_name or peer,
		"user_image": user_image or "",
		# Seconds, not a timestamp: browser and server clocks need not agree.
		"burn_in": max(0, round((get_datetime(doc.burn_at) - now_datetime()).total_seconds(), 1)),
		"saved_by_me": saved_me,
		"saved_by_peer": saved_peer,
	}


def _publish_notice(doc, event=EVENT_BURN_NOTICE):
	for user in (doc.user_a, doc.user_b):
		frappe.publish_realtime(event, _notice_for(doc, user), user=user, after_commit=True)


def _publish_both(doc, event, message):
	for user in (doc.user_a, doc.user_b):
		frappe.publish_realtime(event, message, user=user, after_commit=True)


def _has_messages(doc):
	return bool(
		doc.raven_channel
		and frappe.db.exists("Raven Message", {"channel_id": doc.raven_channel, "message_type": ("!=", "System")})
	)


def _start_parting(doc):
	"""Open → Parting with a fresh countdown; an empty chat simply disappears."""
	if doc.status != "Open":
		return
	if not _has_messages(doc):
		_burn(doc, silent=True)
		return
	burn_at = add_to_date(now_datetime(), seconds=BURN_SECONDS)
	frappe.db.set_value(
		ENCOUNTER_DOCTYPE,
		doc.name,
		{"status": "Parting", "burn_at": burn_at, "saved_by_a": 0, "saved_by_b": 0},
		update_modified=False,
	)
	doc.update({"status": "Parting", "burn_at": burn_at, "saved_by_a": 0, "saved_by_b": 0})
	_publish_notice(doc)


def _cancel_burn(doc):
	if doc.status != "Parting":
		return
	frappe.db.set_value(
		ENCOUNTER_DOCTYPE,
		doc.name,
		{"status": "Open", "burn_at": None, "saved_by_a": 0, "saved_by_b": 0},
		update_modified=False,
	)
	_publish_both(doc, EVENT_BURN_CANCEL, {"encounter": doc.name})


def _delete_permanently(doctype, name):
	# No Deleted Document copy: burned means gone.
	frappe.delete_doc(doctype, name, ignore_permissions=True, force=True, delete_permanently=True)


def _delete_channel(channel):
	"""Delete a Raven channel for good: its messages the Raven way (search index, attached files,
	Raven's own events), and also the threads someone started on them in Raven. A thread is a
	channel of its own, named after its first message; Raven does not delete it with the channel
	(RavenChannel.on_trash: "TODO: Delete all threads"), so "burned" would not mean gone."""
	if not channel or not frappe.db.exists("Raven Channel", channel):
		return
	messages = frappe.get_all("Raven Message", filters={"channel_id": channel}, pluck="name")
	threads = (
		frappe.get_all("Raven Channel", filters={"name": ("in", messages), "is_thread": 1}, pluck="name")
		if messages
		else []
	)
	for thread in threads:
		_delete_channel(thread)
	for message in messages:
		_delete_permanently("Raven Message", message)
	_delete_permanently("Raven Channel", channel)


def _burn(doc, silent=False):
	"""Delete the chat for good: messages, threads, channel, then the encounter."""
	_delete_channel(doc.raven_channel)
	_delete_permanently(ENCOUNTER_DOCTYPE, doc.name)
	if not silent:
		_publish_both(doc, EVENT_BURNED, {"encounter": doc.name})


def _save(doc):
	"""Both said save: move the messages into the two people's Raven DM, unchanged (sender, time,
	files, reactions) and without notifying anyone again; then drop the temporary channel."""
	from raven.api.raven_channel import create_direct_message_channel

	peer = _peer(doc)
	dm_channel = create_direct_message_channel(peer)
	messages = frappe.get_all(
		"Raven Message", filters={"channel_id": doc.raven_channel}, fields=["name", "creation"], order_by="creation"
	)
	names = [m.name for m in messages]
	if names:
		for doctype, field in (("Raven Message", "name"), ("Raven Message Reaction", "message")):
			if not frappe.db.table_exists(doctype):
				continue
			table = frappe.qb.DocType(doctype)
			frappe.qb.update(table).set(table.channel_id, dm_channel).where(table[field].isin(names)).run()
		latest = messages[-1].creation
		current = frappe.db.get_value("Raven Channel", dm_channel, "last_message_timestamp")
		if not current or get_datetime(current) < get_datetime(latest):
			frappe.db.set_value("Raven Channel", dm_channel, "last_message_timestamp", latest, update_modified=False)
		_reindex_messages(names)
	# The temporary channel is empty now; Raven's on_trash removes its members.
	if frappe.db.exists("Raven Channel", doc.raven_channel):
		_delete_permanently("Raven Channel", doc.raven_channel)
	_delete_permanently(ENCOUNTER_DOCTYPE, doc.name)
	_publish_both(doc, EVENT_SAVED, {"encounter": doc.name, "dm_channel": dm_channel})
	return dm_channel


def _reindex_messages(names):
	"""Raven's search index stores the channel of each message: point it at the DM."""
	try:
		from raven.api.search import RavenSearch

		search = RavenSearch()
		for name in names:
			search.index_doc("Raven Message", name)
	except Exception:  # noqa: BLE001
		# No index on this site (or another Raven version): search catches up on its next
		# rebuild. Saving the chat must not fail because of the search index.
		pass


@frappe.whitelist(methods=["POST"])
def part_encounter(encounter):
	"""The two chips walked apart: start the burn notice (both pages call this; once is enough)."""
	_require_user()
	doc = _require_party(encounter, ("Open", "Parting"))
	_start_parting(doc)
	if not frappe.db.exists(ENCOUNTER_DOCTYPE, doc.name):
		return None
	return _notice_for(frappe.db.get_value(ENCOUNTER_DOCTYPE, doc.name, ENCOUNTER_FIELDS, as_dict=True), frappe.session.user)


@frappe.whitelist(methods=["POST"])
def save_encounter(encounter):
	"""I want to keep this chat. Saved for real only when the other person says so too."""
	_require_user()
	# Locking read: when both press Save at the same moment, the second waits for the first and
	# then sees its flag, so one of the two requests does the save (review of the release).
	doc = _require_party(encounter, ("Parting",), for_update=True)
	field = "saved_by_a" if frappe.session.user == doc.user_a else "saved_by_b"
	frappe.db.set_value(ENCOUNTER_DOCTYPE, doc.name, field, 1, update_modified=False)
	doc[field] = 1
	if doc.saved_by_a and doc.saved_by_b:
		return {"saved": True, "dm_channel": _save(doc)}
	_publish_notice(doc, EVENT_SAVE_VOTE)
	peer = _peer(doc)
	if peer in _dummy_users() and frappe.session.user not in _dummy_users():
		# A test dummy agrees, so the save path can be tried alone.
		frappe.enqueue(
			"phamos.api.ophice.dummy_save", queue="short", enqueue_after_commit=True, encounter=doc.name, dummy=peer
		)
	return {"saved": False}


def dummy_save(encounter, dummy):
	"""Background job: a test dummy (site config only) also presses Save."""
	if dummy not in _dummy_users():
		return
	time.sleep(DUMMY_REPLY_DELAY)
	frappe.set_user(dummy)
	try:
		save_encounter(encounter)
	except frappe.ValidationError:
		pass  # burned or met again meanwhile


@frappe.whitelist(methods=["POST"])
def burn_if_due(encounter):
	"""The countdown on the page reached zero: burn now, unless it was saved or met again."""
	_require_user()
	doc = frappe.db.get_value(ENCOUNTER_DOCTYPE, encounter, ENCOUNTER_FIELDS, as_dict=True)
	if not doc or frappe.session.user not in (doc.user_a, doc.user_b):
		return {"burned": True}
	# One second of slack for the page's clock.
	if doc.status == "Parting" and get_datetime(doc.burn_at) <= add_to_date(now_datetime(), seconds=1):
		return {"burned": _burn_or_save(doc) == "burned"}
	return {"burned": False}


def _burn_or_save(doc):
	"""The countdown is over: burned, unless both saved it (a save that raced with the countdown)."""
	if doc.saved_by_a and doc.saved_by_b:
		# _save works from one of the two people's side (their DM): act as user_a.
		user = frappe.session.user
		frappe.set_user(doc.user_a)
		try:
			_save(doc)
		finally:
			frappe.set_user(user)
		return "saved"
	_burn(doc)
	return "burned"


def _each(rows, step, what):
	"""Scheduler: one row at a time. A row that fails (deleted meanwhile, a concurrent save) is
	rolled back to its savepoint and logged; the other rows still get done."""
	for row in rows:
		try:
			frappe.db.savepoint("ophice_row")
			step(row)
		except Exception:
			frappe.db.rollback(save_point="ophice_row")
			frappe.log_error(title=f"Ophice scheduler: {what}", reference_doctype=None)


def burn_due_encounters():
	"""Scheduler, every minute: burn what is overdue, and start the countdown for encounters whose
	other person has left (tab closed, connection gone) without anyone walking away."""
	from phamos.api.ophice_guest import purge_guests

	_each(
		frappe.get_all(
			ENCOUNTER_DOCTYPE,
			filters={"status": "Parting", "burn_at": ("<=", now_datetime())},
			fields=ENCOUNTER_FIELDS,
		),
		_burn_or_save,
		"burn encounter",
	)

	def part_if_alone(doc):
		if not (_position_of(doc.user_a) and _position_of(doc.user_b)):
			_start_parting(doc)

	_each(
		frappe.get_all(ENCOUNTER_DOCTYPE, filters={"status": "Open"}, fields=ENCOUNTER_FIELDS),
		part_if_alone,
		"part encounter",
	)
	_settle_batches()
	# Guest visits that ended (tab closed, 12 hours up) leave nothing behind in Redis (#2080).
	purge_guests()
	frappe.db.commit()


def _my_notices(user):
	rows = frappe.get_all(
		ENCOUNTER_DOCTYPE,
		filters={"status": "Parting"},
		or_filters={"user_a": user, "user_b": user},
		fields=ENCOUNTER_FIELDS,
	)
	return [_notice_for(row, user) for row in rows]


def _part_all_mine(user):
	for doc in frappe.get_all(
		ENCOUNTER_DOCTYPE, filters={"status": "Open"}, or_filters={"user_a": user, "user_b": user}, fields=ENCOUNTER_FIELDS
	):
		_start_parting(doc)


# --- Meeting areas (#2060).


def _allowed_jitsi_domains():
	"""The Jitsi servers areas may point to. The page loads external_api.js from that server, so
	only servers the site trusts: the configured one plus an optional list."""
	domains = {str(frappe.conf.get("ophice_jitsi_domain") or JITSI_DEFAULT_DOMAIN).strip().lower()}
	extra = frappe.conf.get("ophice_jitsi_domains") or []
	if isinstance(extra, list):
		domains |= {str(d).strip().lower() for d in extra if d}
	return domains


def _parse_meeting_url(url):
	"""(domain, room) of https://<allowed Jitsi server>/<room>, or a clear error."""
	from urllib.parse import unquote, urlparse

	parsed = urlparse((url or "").strip())
	domain = (parsed.hostname or "").lower()
	if parsed.port:
		domain = f"{domain}:{parsed.port}"
	room = unquote(parsed.path.strip("/"))
	if parsed.scheme != "https" or not domain:
		frappe.throw(_("The meeting URL must start with https://, for example https://meet.jit.si/OurStandup."))
	if domain not in _allowed_jitsi_domains():
		frappe.throw(
			_("Only meetings on {0} can be used here.").format(", ".join(sorted(_allowed_jitsi_domains())))
		)
	# One path segment of letters, digits, - and _: what Jitsi accepts as a room name.
	if not re.fullmatch(r"[A-Za-z0-9_-]{3,128}", room):
		frappe.throw(_("The meeting URL needs a room name after the server, for example /OurStandup."))
	return domain, room


def _areas():
	areas = frappe.get_all(
		AREA_DOCTYPE,
		fields=[
			"name", "title", "x", "y", "width", "height", "meeting_url", "jitsi_domain", "jitsi_room",
			"color_hue", "chat_mode", "kind", "cockpit",
		],
		order_by="creation asc",
		limit=MAX_AREAS,
	)
	# An area without a stored color (made before colors existed) gets a steady one from its
	# name: this runs on reads, which Frappe does not commit, so nothing random here.
	tiles = None
	for area in areas:
		area.chat_mode = area.chat_mode or "Saved"
		area.kind = area.kind or "Meeting"
		if area.cockpit:
			# The cockpit's app icon, shown on its space (#2076).
			tiles = tiles if tiles is not None else _cockpit_tiles()
			tile = tiles.get(area.cockpit) or {}
			area.cockpit_logo = tile.get("logo", "")
			area.cockpit_title = tile.get("title", "")
			# The tile colour of its icon: the map draws the icon from colour + symbol, so the tile
			# can be see-through while the symbol stays solid (PM, 2026-11-22).
			area.cockpit_color = COCKPIT_COLORS.get(area.cockpit, "")
		if area.color_hue is None or area.color_hue == "":
			area.color_hue = int(hashlib.md5(area.name.encode()).hexdigest(), 16) % 360
	return areas


def _random_hue(taken):
	"""A random hue at least AREA_HUE_GAP degrees from every taken one (if there is still room)."""
	taken = [int(h) % 360 for h in taken]
	free = [
		h for h in range(360) if all(min(abs(h - t), 360 - abs(h - t)) >= AREA_HUE_GAP for t in taken)
	]
	return random.choice(free or range(360))


def _half(value):
	"""Areas snap to half tiles (#2067): the grid for areas has double the resolution."""
	return round(frappe.utils.flt(value) / AREA_STEP) * AREA_STEP


def _clean_rect(x, y, width, height):
	"""A rectangle in half-tile steps inside the grid, at least half a tile each way."""
	x = max(0, min(_cols() - AREA_STEP, _half(x)))
	y = max(0, min(_rows() - AREA_STEP, _half(y)))
	width = max(AREA_STEP, min(_cols() - x, _half(width)))
	height = max(AREA_STEP, min(_rows() - y, _half(height)))
	return x, y, width, height


def _overlaps(name, x, y, width, height):
	for area in _areas():
		if area.name == name:
			continue
		if x < area.x + area.width and area.x < x + width and y < area.y + area.height and area.y < y + height:
			return area.title
	return None


@frappe.whitelist(methods=["POST"])
def save_area(
	title, meeting_url="", x=0, y=0, width=1, height=1, name=None, chat_mode="Saved", kind="Meeting", cockpit=""
):
	"""Create or change a space, for everyone (map editors only, #2071). A meeting space has a
	Jitsi meeting and a chat; the start space (#2072, only one) has neither; a cockpit space
	(#2076) belongs to a cockpit and may have a meeting."""
	_require_map_editor()
	if chat_mode not in CHAT_MODES:
		frappe.throw(_("Unknown chat mode."))
	if kind not in AREA_KINDS:
		frappe.throw(_("Unknown kind of space."))
	title = (title or "").strip()[:AREA_TITLE_LENGTH]
	if not title:
		frappe.throw(_("Give the area a name."))
	if kind in SINGLE_KINDS:
		other = frappe.db.get_value(AREA_DOCTYPE, {"kind": kind, "name": ("!=", name or "")}, "title")
		if other:
			if kind == "Start":
				frappe.throw(_("There is already a start space: {0}.").format(other))
			if kind == "Phriend":
				frappe.throw(_("Phriend already has a place on the map: {0}.").format(other))
			frappe.throw(_("There is already a guest area: {0}.").format(other))
	cockpit = (cockpit or "").strip() if kind == "Cockpit" else ""
	if kind == "Cockpit" and cockpit not in _cockpit_tiles():
		frappe.throw(_("Pick the cockpit this space belongs to."))
	# No meeting: the start space, Phriend's place (#2053), a cockpit space without a link.
	if kind in ("Start", "Phriend") or (kind == "Cockpit" and not (meeting_url or "").strip()):
		domain = room = ""
	else:
		domain, room = _parse_meeting_url(meeting_url)
	x, y, width, height = _clean_rect(x, y, width, height)
	clash = _overlaps(name, x, y, width, height)
	if clash:
		frappe.throw(_("This overlaps the area {0}.").format(clash))
	values = {
		"title": title,
		"kind": kind,
		"meeting_url": f"https://{domain}/{room}" if domain else "",
		"jitsi_domain": domain,
		"jitsi_room": room,
		"x": x,
		"y": y,
		"width": width,
		"height": height,
		"chat_mode": chat_mode,
		"cockpit": cockpit,
	}
	if name:
		if not frappe.db.exists(AREA_DOCTYPE, name):
			frappe.throw(_("This area no longer exists."))
		doc = frappe.get_doc(AREA_DOCTYPE, name)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		if frappe.db.count(AREA_DOCTYPE) >= MAX_AREAS:
			frappe.throw(_("Ophice has room for at most {0} meeting areas.").format(MAX_AREAS))
		values["color_hue"] = _random_hue([a.color_hue for a in _areas()])
		doc = frappe.get_doc({"doctype": AREA_DOCTYPE, **values}).insert(ignore_permissions=True)
	_publish(EVENT_AREAS, {"areas": _areas()})
	return doc.name


@frappe.whitelist(methods=["POST"])
def delete_area(name):
	"""Remove a meeting area, for everyone."""
	_require_map_editor()
	if frappe.db.exists(AREA_DOCTYPE, name):
		# Its chat goes with it: the batches only make sense inside the area.
		for batch in frappe.get_all(BATCH_DOCTYPE, filters={"area": name}, pluck="name"):
			_burn_batch(frappe.get_doc(BATCH_DOCTYPE, batch))
		frappe.delete_doc(AREA_DOCTYPE, name, ignore_permissions=True)
	_publish(EVENT_AREAS, {"areas": _areas()})


# --- Area chat (#2062, #2066): every meeting area has a chat, for whoever stands in it.
#
# The chat comes in batches: one batch per meeting, from two people in the area until it is
# empty, each with its own private Raven channel. When the area empties, the batch waits
# BATCH_GRACE_MINUTES (a lost connection must not lose the chat); a participant who steps back in
# continues it. Then mode Saved keeps it, mode Not saved deletes it unless someone saved it.
# Confidential stores nothing: messages go over realtime to the people in the area right now.
# Save and Burn are a vote among the batch's participants; a tie keeps the batch.


def _inside_area(area, user):
	position = _position_of(user)
	if not position:
		return False
	cx, cy = position[0] + 0.5, position[1] + 0.5
	return (
		area.x - AREA_SLACK <= cx < area.x + area.width + AREA_SLACK
		and area.y - AREA_SLACK <= cy < area.y + area.height + AREA_SLACK
	)


def _people_in(area, exclude=None):
	"""The users standing in an area. Guests (#2080) are not users: they never join an employee
	meeting's chat batch or its Raven channel."""
	return [
		c["user"]
		for c in _online()
		if c["user"] != exclude and not c.get("guest") and _inside_area(area, c["user"])
	]


def _area(name):
	if not name or not frappe.db.exists(AREA_DOCTYPE, name):
		frappe.throw(_("This area no longer exists."))
	area = frappe.get_doc(AREA_DOCTYPE, name)
	area.chat_mode = area.chat_mode or "Saved"
	return area


def _require_inside(name):
	"""The area, if I stand in it: being there is the permission to read and write its chat."""
	area = _area(name)
	if (area.kind or "Meeting") not in AREA_CHAT_KINDS or not area.jitsi_room and area.kind == "Cockpit":
		frappe.throw(_("This space has no chat."))
	if not _inside_area(area, frappe.session.user):
		frappe.throw(_("Step into the area to use its chat."), frappe.PermissionError)
	return area


def _clean_text(text):
	text = (text or "").strip()
	if not text:
		frappe.throw(_("Write something first."))
	if len(text) > MAX_MESSAGE_LENGTH:
		frappe.throw(_("A message can be at most {0} characters.").format(MAX_MESSAGE_LENGTH))
	return text


def _running_batch_name(area_name, for_update=False):
	return frappe.db.get_value(
		BATCH_DOCTYPE,
		{"area": area_name, "status": ("in", ("Open", "Ending"))},
		"name",
		order_by="creation desc",
		for_update=for_update,
	)


def _new_batch(area):
	"""A new batch with its own private Raven channel (no members yet)."""
	from phamos.api.issue_chat import _resolve_workspace

	channel = frappe.get_doc(
		{
			"doctype": "Raven Channel",
			"channel_name": f"ophice-area-{frappe.generate_hash(length=8)}",
			"channel_description": _("Ophice area chat: {0}").format(area.title),
			"type": "Private",
			"workspace": _resolve_workspace(),
		}
	)
	channel.flags.do_not_add_member = True
	channel.insert(ignore_permissions=True)
	return frappe.get_doc(
		{
			"doctype": BATCH_DOCTYPE,
			"area": area.name,
			"status": "Open",
			"raven_channel": channel.name,
			"started_at": now_datetime(),
		}
	).insert(ignore_permissions=True)


def _current_batch(area, create):
	"""The area's running batch, with everyone inside as a participant. A new one is made when
	`create` is set; an Ending one continues (somebody came back during the grace time)."""
	from phamos.api.issue_chat import _ensure_members

	name = _running_batch_name(area.name)
	if not name and not create:
		return None
	# Two people stepping in at once must not make two batches.
	_lock_pair(f"area:{area.name}")
	name = _running_batch_name(area.name, for_update=True)
	batch = frappe.get_doc(BATCH_DOCTYPE, name, for_update=True) if name else _new_batch(area)
	people = list(dict.fromkeys([frappe.session.user, *_people_in(area)]))
	known = {p.user for p in batch.participants}
	new = [user for user in people if user not in known]
	for user in new:
		batch.append("participants", {"user": user})
	changed = _sync_inside(batch, people) or batch.status == "Ending"
	if batch.status == "Ending":
		batch.status = "Open"
		batch.grace_until = None
	if changed:
		batch.save(ignore_permissions=True)
	if new:
		_ensure_members(frappe.get_doc("Raven Channel", batch.raven_channel), new, admin=frappe.session.user, silent=True)
	if changed:
		_notify_batch(batch)
	return batch


def _sync_inside(batch, people):
	"""Joined and Left events for the timeline: compare who stands in the area with who did.
	True when something changed (the caller saves)."""
	inside = set(people)
	changed = False
	for row in batch.participants:
		now_in = row.user in inside
		if bool(row.inside) == now_in:
			continue
		row.inside = 1 if now_in else 0
		batch.append("events", {"user": row.user, "event": "Joined" if now_in else "Left", "at": now_datetime()})
		changed = True
	return changed


def _seconds_until(value):
	"""Seconds from now (negative: past), so a browser in any time zone can count from its own clock."""
	return round((get_datetime(value) - now_datetime()).total_seconds()) if value else None


def _batch_row(batch, user, messages=True):
	votes = [p.vote for p in batch.participants]
	row = {
		"name": batch.name,
		"area": batch.area,
		"status": batch.status,
		"saved": bool(batch.saved),
		"started_at": str(batch.started_at),
		"grace_until": str(batch.grace_until) if batch.grace_until else None,
		"vote_until": str(batch.vote_until) if batch.vote_until else None,
		"started_in": _seconds_until(batch.started_at),
		"grace_in": _seconds_until(batch.grace_until),
		"vote_in": _seconds_until(batch.vote_until),
		"participants": [p.user for p in batch.participants],
		"names": {p.user: frappe.utils.get_fullname(p.user) for p in batch.participants},
		"mine": any(p.user == user for p in batch.participants),
		"my_vote": next((p.vote for p in batch.participants if p.user == user), "") or "",
		"keep_votes": votes.count("Keep"),
		"burn_votes": votes.count("Burn"),
	}
	if messages:
		rows = _messages(batch.raven_channel) if batch.raven_channel else []
		for message in rows:
			message["at_in"] = _seconds_until(message["creation"])
		row["messages"] = rows
		# Messages and who joined or left, in time order (#2066).
		events = [
			{
				"type": "event",
				"name": e.name,
				"user": e.user,
				"event": e.event,
				"creation": str(e.at),
				"at_in": _seconds_until(e.at),
			}
			for e in batch.events
		]
		row["timeline"] = sorted([{"type": "message", **m} for m in rows] + events, key=lambda r: get_datetime(r["creation"]))
	return row


def _area_batches(area):
	"""The area's batches, oldest first: what is kept plus the running one."""
	names = frappe.get_all(
		BATCH_DOCTYPE,
		filters={"area": area.name},
		pluck="name",
		order_by="started_at desc",
		limit=BATCHES_SHOWN,
	)
	return [frappe.get_doc(BATCH_DOCTYPE, name) for name in reversed(names)]


def _notify_batch(batch_or_area, extra=()):
	"""Tell the participants and the people in the area to reload: a batch changed."""
	if isinstance(batch_or_area, str):
		area_name, users = batch_or_area, set()
	else:
		area_name = batch_or_area.area
		users = {p.user for p in batch_or_area.participants}
	if frappe.db.exists(AREA_DOCTYPE, area_name):
		users |= set(_people_in(_area(area_name)))
	for user in users | set(extra):
		frappe.publish_realtime(EVENT_AREA_BATCHES, {"area": area_name}, user=user, after_commit=True)


@frappe.whitelist(methods=["POST"])
def get_area_chat(area):
	"""The chat of the area I stand in: its mode and its batches (kept ones and the running one)."""
	_require_user()
	doc = _require_inside(area)
	user = frappe.session.user
	if doc.chat_mode != "Confidential":
		# Two people inside: a meeting, so its batch starts (or continues).
		_current_batch(doc, create=len(set([user, *_people_in(doc)])) >= 2)
	return {
		"area": doc.name,
		"mode": doc.chat_mode,
		"batches": [_batch_row(b, user) for b in _area_batches(doc)],
	}


@frappe.whitelist(methods=["POST"])
def send_area_message(area, text):
	"""Write into the chat of the area I stand in; everyone in the area gets it right away."""
	_require_user()
	text = _clean_text(text)
	doc = _require_inside(area)
	user = frappe.session.user
	batch = None
	if doc.chat_mode == "Confidential":
		# Never written anywhere: only relayed to the people in the area now.
		row = {"name": frappe.generate_hash(length=12), "owner": user, "text": text, "creation": str(now_datetime())}
		after_commit = False
	else:
		batch = _current_batch(doc, create=True)
		message = frappe.get_doc(
			{
				"doctype": "Raven Message",
				"channel_id": batch.raven_channel,
				"message_type": "Text",
				"text": "<p>{}</p>".format(escape_html(text).replace("\n", "<br>")),
			}
		).insert(ignore_permissions=True)
		row = _message_row(message)
		after_commit = True
	row["at_in"] = 0
	payload = {"area": doc.name, "batch": batch.name if batch else None, "message": row}
	for person in {user, *_people_in(doc)}:
		frappe.publish_realtime(EVENT_AREA_MESSAGE, payload, user=person, after_commit=after_commit)
	return {**row, "batch": payload["batch"]}


def _start_ending(batch):
	batch.status = "Ending"
	batch.grace_until = add_to_date(now_datetime(), minutes=BATCH_GRACE_MINUTES)
	batch.save(ignore_permissions=True)
	_notify_batch(batch)


@frappe.whitelist(methods=["POST"])
def leave_area(area):
	"""I walked out of an area: when nobody is left, its batch's grace time starts."""
	_require_user()
	if not area or not frappe.db.exists(AREA_DOCTYPE, area):
		return False
	doc = _area(area)
	name = _running_batch_name(doc.name)
	if not name:
		return False
	batch = frappe.get_doc(BATCH_DOCTYPE, name)
	still_inside = _people_in(doc, exclude=frappe.session.user)
	if _sync_inside(batch, still_inside):
		batch.save(ignore_permissions=True)
		_notify_batch(batch)
	if still_inside or batch.status != "Open":
		return False
	_start_ending(batch)
	return True


def _burn_batch(batch):
	"""Delete the batch, its messages, threads and channel for good."""
	_delete_channel(batch.raven_channel)
	_notify_batch(batch)
	_delete_permanently(BATCH_DOCTYPE, batch.name)


def _decide_vote(batch, timed_out=False):
	"""The majority of the votes cast decides; a tie (or no votes) keeps the batch.

	A kept chat (history of an earlier meeting) is burned at the end of the vote time only by a
	majority of everyone who was there: one person's Burn plus everyone else's silence keeps it
	(review of the release; no data loss by accident)."""
	votes = [p.vote for p in batch.participants]
	burn = votes.count("Burn") > votes.count("Keep")
	if burn and timed_out and batch.status == "Kept":
		burn = votes.count("Burn") * 2 > len(batch.participants)
	if burn:
		_burn_batch(batch)
		return "burned"
	batch.saved = 1
	batch.vote_until = None
	for p in batch.participants:
		p.vote = ""
	batch.save(ignore_permissions=True)
	_notify_batch(batch)
	return "kept"


@frappe.whitelist(methods=["POST"])
def vote_batch(batch, vote):
	"""Save (Keep) or Burn a batch I took part in. The first vote opens a vote for all participants;
	it is decided when everyone voted, or after BATCH_VOTE_HOURS by the votes cast."""
	_require_user()
	if vote not in ("Keep", "Burn"):
		frappe.throw(_("Vote Keep or Burn."))
	if not batch or not frappe.db.exists(BATCH_DOCTYPE, batch):
		frappe.throw(_("This chat no longer exists."))
	doc = frappe.get_doc(BATCH_DOCTYPE, batch, for_update=True)
	user = frappe.session.user
	mine = next((p for p in doc.participants if p.user == user), None)
	if not mine:
		frappe.throw(_("Only the people who were in this meeting can decide about its chat."), frappe.PermissionError)
	if not doc.vote_until:
		doc.vote_until = add_to_date(now_datetime(), hours=BATCH_VOTE_HOURS)
	mine.vote = vote
	if vote == "Keep":
		# Anyone can save: a saved batch survives the grace time of a Not saved area.
		doc.saved = 1
	if all(p.vote for p in doc.participants):
		return {"result": _decide_vote(doc)}
	doc.save(ignore_permissions=True)
	_notify_batch(doc)
	return {"result": "voting", "batch": _batch_row(doc, user, messages=False)}


@frappe.whitelist()
def get_batch_notices():
	"""Meeting chats that need me, wherever I am on the map (#2066, #2091): only when there is
	something to decide: messages that will be deleted unless someone saves them, or a Keep/Burn
	vote without my vote. A chat that is kept anyway, or has no messages, is not a notice."""
	_require_user()
	user = frappe.session.user
	mine = frappe.get_all(
		"Ophice Chat Batch Participant",
		filters={"user": user, "parenttype": BATCH_DOCTYPE},
		pluck="parent",
	)
	# Only those that can need me (grace time or a vote), not every kept chat I was ever in.
	names = (
		frappe.get_all(
			BATCH_DOCTYPE,
			filters={"name": ("in", list(set(mine)))},
			or_filters={"status": "Ending", "vote_until": ("is", "set")},
			pluck="name",
		)
		if mine
		else []
	)
	notices = []
	for name in names:
		batch = frappe.get_doc(BATCH_DOCTYPE, name)
		if not batch.raven_channel or not frappe.db.exists(
			"Raven Message", {"channel_id": batch.raven_channel, "message_type": ("!=", "System")}
		):
			continue
		row = _batch_row(batch, user, messages=False)
		mode = frappe.db.get_value(AREA_DOCTYPE, batch.area, "chat_mode") or "Saved"
		deleted_soon = batch.status == "Ending" and mode != "Saved" and not batch.saved
		my_vote_missing = bool(batch.vote_until) and not row["my_vote"]
		if deleted_soon or my_vote_missing:
			row["area_title"] = frappe.db.get_value(AREA_DOCTYPE, batch.area, "title")
			row["mode"] = mode
			notices.append(row)
	return sorted(notices, key=lambda r: r["started_at"])


def _settle_batches():
	"""Scheduler: start the grace time of meetings nobody is in any more (tabs closed), end grace
	times and decide votes that are due."""
	now = now_datetime()

	def check_open(name):
		batch = frappe.get_doc(BATCH_DOCTYPE, name, for_update=True)
		if not frappe.db.exists(AREA_DOCTYPE, batch.area):
			_burn_batch(batch)
			return
		people = _people_in(_area(batch.area))
		if _sync_inside(batch, people):
			batch.save(ignore_permissions=True)
			_notify_batch(batch)
		if not people:
			_start_ending(batch)

	def end_grace(name):
		batch = frappe.get_doc(BATCH_DOCTYPE, name, for_update=True)
		area = _area(batch.area) if frappe.db.exists(AREA_DOCTYPE, batch.area) else None
		if area and _people_in(area):
			return  # somebody is back; their page continues the batch
		if area and (area.chat_mode == "Saved" or batch.saved):
			batch.status = "Kept"
			batch.grace_until = None
			batch.save(ignore_permissions=True)
			_notify_batch(batch)
		else:
			_burn_batch(batch)

	def end_vote(name):
		if frappe.db.exists(BATCH_DOCTYPE, name):
			_decide_vote(frappe.get_doc(BATCH_DOCTYPE, name, for_update=True), timed_out=True)

	_each(frappe.get_all(BATCH_DOCTYPE, filters={"status": "Open"}, pluck="name"), check_open, "open batch")
	_each(
		frappe.get_all(BATCH_DOCTYPE, filters={"status": "Ending", "grace_until": ("<=", now)}, pluck="name"),
		end_grace,
		"end grace",
	)
	_each(frappe.get_all(BATCH_DOCTYPE, filters={"vote_until": ("<=", now)}, pluck="name"), end_vote, "end vote")


# --- People list (#2063): all Raven users, online first, with what they are doing.
#
# Live only: presence from the Redis cache, nothing is logged. "Hide my details" leaves only name,
# picture and online/offline; an encounter shows as "in a chat", never with whom.


def _hides_details(user):
	raw = frappe.db.get_value("DefaultValue", {"parent": user, "defkey": HIDE_KEY}, "defvalue")
	return raw == "1"


def _in_encounter(users):
	"""The users among `users` who are in an open encounter right now."""
	if not users:
		return set()
	rows = frappe.get_all(
		ENCOUNTER_DOCTYPE,
		filters={"status": "Open"},
		or_filters={"user_a": ("in", list(users)), "user_b": ("in", list(users))},
		fields=["user_a", "user_b"],
	)
	return {u for r in rows for u in (r.user_a, r.user_b)} & set(users)


@frappe.whitelist()
def get_people():
	"""All Raven users, online in Ophice first, with their status (as far as they show it)."""
	_require_user()
	me = frappe.session.user
	users = frappe.get_all(
		"Raven User",
		filters={"type": "User", "enabled": 1},
		fields=["user", "full_name", "user_image"],
		limit=500,
	)
	online = {c["user"]: c for c in _online()}
	# Only meeting spaces say where someone is; standing in the start space is just "around".
	areas = [a for a in _areas() if a.kind in MEETING_KINDS]
	working = _working_on([u.user for u in users if u.user == me or not _hides_details(u.user)])
	cockpits = _cockpits_now()
	chatting = _in_encounter([u.user for u in users if u.user in online])
	people = []
	for row in users:
		if not row.user or row.user == "Guest":
			continue
		hidden = _hides_details(row.user)
		chip = online.get(row.user)
		person = {
			"user": row.user,
			"full_name": row.full_name or row.user,
			"user_image": row.user_image or "",
			"online": bool(chip),
			"hidden": hidden,
			"status": _status_of(row.user),
			"area": "",
			"in_chat": False,
			# What they work on now (#2064): the Implementation, the issue only as a detail.
			"working_on": working.get(row.user),
			"cockpit": cockpits.get(row.user) if (row.user == me or not hidden) else None,
		}
		if chip and (not hidden or row.user == me):
			cx, cy = chip["x"] + 0.5, chip["y"] + 0.5
			area = next((a for a in areas if a.x <= cx < a.x + a.width and a.y <= cy < a.y + a.height), None)
			person["area"] = area.title if area else ""
			person["in_chat"] = row.user in chatting
		people.append(person)
	people.sort(key=lambda p: (not p["online"], p["user"] != me, (p["full_name"] or "").lower()))
	# Guests on the map (#2082): first, so nobody overlooks a visitor.
	from phamos.api.ophice_guest import online_guests

	return {"people": online_guests() + people, "hide_details": _hides_details(me)}


@frappe.whitelist(methods=["POST"])
def set_auto_cockpit(on=1):
	"""Cockpit spaces (#2076): open the cockpit when I stop in its space, or not."""
	_require_user()
	if frappe.utils.cint(on):
		frappe.defaults.clear_user_default(AUTO_COCKPIT_KEY, frappe.session.user)
	else:
		frappe.defaults.set_user_default(AUTO_COCKPIT_KEY, "1", frappe.session.user)
	return bool(frappe.utils.cint(on))


def _auto_cockpit(user):
	return frappe.db.get_value("DefaultValue", {"parent": user, "defkey": AUTO_COCKPIT_KEY}, "defvalue") != "1"


@frappe.whitelist()
def cockpit_choices():
	"""Map editors: the cockpits a space can belong to (all of them, not only mine)."""
	_require_map_editor()
	return sorted(_cockpit_tiles().values(), key=lambda c: c["title"])


@frappe.whitelist()
def new_meeting_url():
	"""Map editors: a ready meeting URL for a new space (#2094), on the site's Jitsi server with an
	unguessable room like the encounters get. The space creator fills it in; it stays editable."""
	_require_map_editor()
	domain = str(frappe.conf.get("ophice_jitsi_domain") or JITSI_DEFAULT_DOMAIN).strip().strip("/").lower()
	return f"https://{domain}/{_new_jitsi_room()}"


@frappe.whitelist(methods=["POST"])
def set_hide_details(hide=0):
	"""Show or hide what I am doing (place, chat, work, cockpit) in the people list."""
	_require_user()
	hide = frappe.utils.cint(hide)
	if hide:
		frappe.defaults.set_user_default(HIDE_KEY, "1", frappe.session.user)
		frappe.cache.hdel(COCKPIT_CACHE_KEY, frappe.session.user)
	else:
		frappe.defaults.clear_user_default(HIDE_KEY, frappe.session.user)
	return bool(hide)


def _as_instant(value):
	"""A stored time (the site's system time zone, no zone attached) as an ISO instant with its
	offset, so the browser computes "5 minutes ago" right in any time zone (AI review of !1301)."""
	if not value:
		return ""
	moment = get_datetime(value)
	if moment.tzinfo is None:
		moment = moment.replace(tzinfo=ZoneInfo(frappe.utils.get_system_timezone()))
	return moment.isoformat()


@frappe.whitelist()
def get_chat_options(user):
	"""Where I can chat with `user`: our direct message (if any) and our latest shared channels."""
	from phamos.api.issue_chat import _raven_user, channel_url

	_require_user()
	me = frappe.session.user
	if not _raven_user(me):
		frappe.throw(_("You can't chat: no Raven access."))
	other = _raven_user(user)
	if not other or user == me:
		frappe.throw(_("{0} can't chat: no Raven access.").format(frappe.utils.get_fullname(user)))
	dm_1, dm_2 = (me, user) if me > user else (user, me)
	dm = frappe.db.get_value(
		"Raven Channel",
		{"is_direct_message": 1, "dm_user_1": dm_1, "dm_user_2": dm_2},
		["name", "last_message_timestamp"],
		as_dict=True,
	)
	# Channels we are both members of; not threads, not archived, not temporary encounters.
	member = frappe.qb.DocType("Raven Channel Member")
	other_member = frappe.qb.DocType("Raven Channel Member").as_("other_member")
	channel = frappe.qb.DocType("Raven Channel")
	rows = (
		frappe.qb.from_(member)
		.join(other_member)
		.on(other_member.channel_id == member.channel_id)
		.join(channel)
		.on(channel.name == member.channel_id)
		.select(
			channel.name, channel.channel_name, channel.channel_description, channel.workspace, channel.type,
			channel.last_message_timestamp,
		)
		.where(member.user_id == _raven_user(me))
		.where(other_member.user_id == other)
		.where(channel.is_direct_message == 0)
		.where(channel.is_thread == 0)
		.where(channel.is_archived == 0)
		.where(channel.channel_name.not_like("encounter-%"))
		.orderby(channel.last_message_timestamp, order=frappe.qb.desc)
		.limit(RECENT_CHATS)
		.run(as_dict=True)
	)
	chats = [
		{
			# Issue and area chats describe themselves ("ISS-…: subject"); others go by their name.
			"label": (r.channel_description or r.channel_name or "").strip()[:80],
			"type": r.type,
			"last_message_at": _as_instant(r.last_message_timestamp),
			"url": channel_url(r.workspace, r.name),
		}
		for r in rows
	]
	return {
		"dm": {"url": f"/raven/dm-channel/{dm.name}", "last_message_at": _as_instant(dm.last_message_timestamp)}
		if dm
		else None,
		"chats": chats,
	}


@frappe.whitelist(methods=["POST"])
def start_direct_message(user):
	"""Our direct message channel (Raven makes it if it does not exist yet), as a link."""
	from raven.api.raven_channel import create_direct_message_channel

	_require_user()
	return {"url": f"/raven/dm-channel/{create_direct_message_channel(user)}"}


# --- What someone works on right now (#2064): the running timer's Implementation.
#
# PM: the specific task is not important, the Implementation is. So the card names the
# Implementation and its customer; the GitLab issue is a small link; goal and task text stay
# private. Only a timer that runs now counts (a paused one does not).


def _working_on(users):
	"""user → {implementation, customer_name, project_name, url, issue} for running timers."""
	if not users:
		return {}
	record = frappe.qb.DocType("Timesheet Record")
	item = frappe.qb.DocType("Timesheet Record Item")
	employee = frappe.qb.DocType("Employee")
	rows = (
		frappe.qb.from_(record)
		.join(item)
		.on((item.parent == record.name) & (item.parenttype == "Timesheet Record"))
		.join(employee)
		.on(employee.name == record.employee)
		.select(employee.user_id, record.project, record.gitlab_issue, item.from_time)
		.where(employee.user_id.isin(list(users)))
		.where(record.docstatus == 0)
		.where(item.to_time.isnull())
		.orderby(item.from_time, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	result = {}
	for row in rows:
		if row.user_id in result or not row.project:
			continue
		project = frappe.db.get_value("Project", row.project, ["project_name", "custom_implementation"], as_dict=True)
		if not project:
			continue
		card = {
			"implementation": project.custom_implementation or "",
			"customer_name": "",
			"project_name": project.project_name or row.project,
			"url": "",
			"issue": None,
		}
		if project.custom_implementation:
			customer = frappe.db.get_value("Implementation", project.custom_implementation, "customer")
			card["customer_name"] = (frappe.db.get_value("Customer", customer, "customer_name") if customer else "") or ""
			card["url"] = "/app/implementation/" + quote(project.custom_implementation, safe="")
		if row.gitlab_issue:
			title, url = frappe.db.get_value("GitLab Issue", row.gitlab_issue, ["title", "issue_url"]) or ("", "")
			if url and str(url).startswith("https://"):
				card["issue"] = {"title": title or row.gitlab_issue, "url": url}
		result[row.user_id] = card
	return result


# --- The cockpit someone is in (#2065).
#
# Every cockpit page sends cockpit_heartbeat while its tab is visible; the Redis hash keeps the
# latest one per user for COCKPIT_TTL seconds. Nothing in the database, no history; users who
# hide their details are not recorded at all.


def _cockpit_tiles():
	"""route → {title, logo} from the Apps screen tiles."""
	from phamos.cockpits.settings import COCKPITS

	tiles = {}
	for tile in frappe.get_hooks("add_to_apps_screen", app_name="phamos"):
		route = tile.get("route")
		if route in COCKPITS:
			tiles[route] = {"route": route, "title": _(tile.get("title") or route), "logo": tile.get("logo") or ""}
	return tiles


@frappe.whitelist()
def get_cockpits():
	"""The cockpits I may open from Ophice's shortcut bar (#2073): the Apps screen's, with their
	icons, Personal Cockpit first."""
	_require_user()
	from phamos.www.spa_boot import user_cockpits

	tiles = _cockpit_tiles()
	cockpits = [{**c, "title": _(c["title"]), "logo": tiles.get(c["route"], {}).get("logo", "")} for c in user_cockpits()]
	return sorted(cockpits, key=lambda c: c["route"] != "/personal-cockpit")


@frappe.whitelist(methods=["POST"])
def cockpit_heartbeat(route):
	"""I am looking at the cockpit at `route` (its base route, e.g. /sales-cockpit)."""
	if frappe.session.user == "Guest" or not check_app_permission():
		return False
	user = frappe.session.user
	if route not in _cockpit_tiles() or _hides_details(user):
		frappe.cache.hdel(COCKPIT_CACHE_KEY, user)
		return False
	frappe.cache.hset(COCKPIT_CACHE_KEY, user, {"route": route, "ts": time.time()})
	return True


def _cockpits_now():
	"""user → {route, title, logo} for cockpit tabs seen within COCKPIT_TTL."""
	tiles = _cockpit_tiles()
	now = time.time()
	result = {}
	for user, entry in (frappe.cache.hgetall(COCKPIT_CACHE_KEY) or {}).items():
		user = frappe.safe_decode(user)
		if not isinstance(entry, dict) or now - entry.get("ts", 0) > COCKPIT_TTL or entry.get("route") not in tiles:
			frappe.cache.hdel(COCKPIT_CACHE_KEY, user)
			continue
		result[user] = tiles[entry["route"]]
	return result
