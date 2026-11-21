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

import html
import json
import math
import random
import re
import time

import frappe
from frappe import _
from frappe.utils import escape_html, now_datetime, strip_html

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
EVENT_MESSAGE = "chip_space_message"

# Encounters (#2056): two chips closer than ENCOUNTER_DISTANCE (centres, in tiles) meet. The
# server allows some slack, since positions it knows may be a few hundred ms old.
ENCOUNTER_DISTANCE = 1.2
SERVER_DISTANCE_SLACK = 1.5
ENCOUNTER_DOCTYPE = "Chip Space Encounter"
MAX_MESSAGE_LENGTH = 2000
MESSAGES_SHOWN = 100


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


def _pair_key(user_a, user_b):
	return "|".join(sorted((user_a, user_b)))


def _open_encounter_name(pair_key):
	return frappe.db.get_value(ENCOUNTER_DOCTYPE, {"pair_key": pair_key, "status": "Open"}, "name")


def _require_party(encounter):
	"""The encounter, if the session user is one of its two people and it is still open."""
	doc = frappe.db.get_value(
		ENCOUNTER_DOCTYPE, encounter, ["name", "user_a", "user_b", "status", "raven_channel"], as_dict=True
	)
	if not doc or frappe.session.user not in (doc.user_a, doc.user_b):
		frappe.throw(_("This chat is not yours."), frappe.PermissionError)
	if doc.status != "Open":
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
			"channel_description": _("Chip Space encounter, {0}").format(now_datetime().strftime("%Y-%m-%d %H:%M")),
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
		filters={"channel_id": channel, "message_type": ("!=", "System"), "is_thread": 0},
		fields=["name", "owner", "text", "creation"],
		order_by="creation desc",
		limit=MESSAGES_SHOWN,
	)
	return [_message_row(r) for r in reversed(rows)]


def _encounter_payload(doc):
	return {
		"encounter": doc.name,
		"with": _peer(doc),
		"channel": doc.raven_channel,
		"messages": _messages(doc.raven_channel),
	}


@frappe.whitelist(methods=["POST"])
def open_encounter(with_user):
	"""Two chips met: get or start the encounter chat of the pair and return it with its messages.

	Both pages notice the meeting and both call this; the pair key's unique index makes sure
	only one encounter is created.
	"""
	_require_user()
	me = frappe.session.user
	if not isinstance(with_user, str) or with_user == me or not frappe.db.get_value("User", with_user, "enabled"):
		frappe.throw(_("Nobody to chat with here."))
	mine, theirs = _position_of(me), _position_of(with_user)
	if not mine or not theirs or math.dist(mine, theirs) > ENCOUNTER_DISTANCE + SERVER_DISTANCE_SLACK:
		frappe.throw(_("Move closer to chat."))

	pair_key = _pair_key(me, with_user)
	name = _open_encounter_name(pair_key)
	if not name:
		user_a, user_b = sorted((me, with_user))
		doc = frappe.get_doc(
			{
				"doctype": ENCOUNTER_DOCTYPE,
				"user_a": user_a,
				"user_b": user_b,
				"status": "Open",
				"opened_at": now_datetime(),
				"pair_key": pair_key,
			}
		)
		try:
			doc.insert(ignore_permissions=True)
		except frappe.DuplicateEntryError:
			# The other page was a moment faster.
			frappe.db.rollback()
			name = _open_encounter_name(pair_key)
		else:
			doc.db_set("raven_channel", _create_channel(user_a, user_b), update_modified=False)
			name = doc.name
	return _encounter_payload(_require_party(name))


@frappe.whitelist()
def get_encounter(encounter):
	"""An open encounter of mine, with its latest messages."""
	_require_user()
	return _encounter_payload(_require_party(encounter))


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
			"phamos.api.chip_space.dummy_reply",
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
	"""Background job: a test dummy (site config only) answers "Yes" or "No" at random."""
	if dummy not in _dummy_users():
		return
	time.sleep(DUMMY_REPLY_DELAY)  # a moment to "think", so it reads like a reply
	frappe.set_user(dummy)
	try:
		send_encounter_message(encounter, random.choice((_("Yes"), _("No"))))
	except frappe.ValidationError:
		# The encounter ended meanwhile.
		pass
