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
from frappe.utils import add_to_date, escape_html, get_datetime, now_datetime, strip_html

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
EVENT_BACKGROUND = "chip_space_background"

# The Space's background image: one for everyone, any Space user may change it (PM, 2026-11-21).
# Stored as a global default {"url", "file"}; the previous image's File is deleted on change.
BACKGROUND_KEY = "phamos_chip_space_background"
BACKGROUND_MAX_BYTES = 5 * 1024 * 1024
# Checked by opening the image, not by the file name: no SVG (scripts), no disguised files.
BACKGROUND_FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif"}

# Encounters (#2056): two chips closer than ENCOUNTER_DISTANCE (centres, in tiles) meet. The
# server allows some slack, since positions it knows may be a few hundred ms old.
ENCOUNTER_DISTANCE = 1.2
SERVER_DISTANCE_SLACK = 1.5
ENCOUNTER_DOCTYPE = "Chip Space Encounter"
MAX_MESSAGE_LENGTH = 2000
MESSAGES_SHOWN = 100

# Burn notice (#2057): after parting, the chat burns this many seconds later unless both save it.
BURN_SECONDS = 60
EVENT_BURN_NOTICE = "chip_space_burn_notice"
EVENT_BURN_CANCEL = "chip_space_burn_cancel"
EVENT_SAVE_VOTE = "chip_space_save_vote"
EVENT_SAVED = "chip_space_saved"
EVENT_BURNED = "chip_space_burned"

# Video call on encounter (#2059): a Jitsi room per encounter, joined muted with the camera off.
# Site config: "chip_space_jitsi_domain" (default meet.jit.si), "chip_space_video": 0 turns it off.
JITSI_DEFAULT_DOMAIN = "meet.jit.si"


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
		# Burn notices still running for me (#2057), e.g. after a reload.
		"notices": _my_notices(user),
		"background": _background().get("url") or "",
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
	# Leaving the page is parting from everyone I was chatting with (#2057).
	_part_all_mine(user)


@frappe.whitelist(methods=["POST"])
def save_my_position(x, y):
	"""Remember where my chip stands; values outside the grid are moved onto its edge."""
	_require_user()
	position = {"x": _clamp(x, COLS), "y": _clamp(y, ROWS)}
	frappe.defaults.set_user_default(POSITION_KEY, json.dumps(position, separators=(",", ":")))
	return position


# --- Background image of the Space (shared).


def _background():
	# Read from the table, not frappe.db.get_default(): its Redis cache survives a rollback and
	# could show a background whose File was never committed.
	raw = frappe.db.get_value("DefaultValue", {"parent": "__default", "defkey": BACKGROUND_KEY}, "defvalue")
	try:
		value = json.loads(raw or "{}")
	except (TypeError, ValueError):
		value = {}
	return value if isinstance(value, dict) else {}


def _set_background(value):
	previous = _background().get("file")
	frappe.db.set_default(BACKGROUND_KEY, json.dumps(value, separators=(",", ":")) if value else "")
	if previous and previous != value.get("file") and frappe.db.exists("File", previous):
		frappe.delete_doc("File", previous, ignore_permissions=True, delete_permanently=True)
	_publish(EVENT_BACKGROUND, {"url": value.get("url", ""), "by": frappe.session.user})


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
			image.verify()
	except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
		frappe.throw(_("This file is not an image the Space can show (PNG, JPEG, WebP or GIF)."))
	extension = BACKGROUND_FORMATS.get(image_format)
	if not extension:
		frappe.throw(_("This file is not an image the Space can show (PNG, JPEG, WebP or GIF)."))
	stem = re.sub(r"[^A-Za-z0-9_-]+", "-", (filename or "").rsplit(".", 1)[0]).strip("-")[:60] or "background"
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"chip-space-{stem}.{extension}",
			"content": content,
			# Public: every Space user loads it as a CSS background (see "Verify before production").
			"is_private": 0,
			"folder": "Home",
		}
	).insert(ignore_permissions=True)
	_set_background({"url": file_doc.file_url, "file": file_doc.name})
	return file_doc.file_url


@frappe.whitelist(methods=["POST"])
def upload_background():
	"""Upload an image (multipart field "file") as the Space's background, for everyone."""
	_require_user()
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(_("Choose an image first."))
	# One byte more than allowed is enough to know it is too big.
	content = upload.stream.read(BACKGROUND_MAX_BYTES + 1)
	return {"url": _store_background(content, upload.filename)}


@frappe.whitelist(methods=["POST"])
def remove_background():
	"""Back to the plain grid, for everyone."""
	_require_user()
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


def _pair_key(user_a, user_b):
	return "|".join(sorted((user_a, user_b)))


def _open_encounter_name(pair_key, for_update=False):
	# Open or Parting: the record exists only until it is saved or burned. `for_update` is a
	# locking read: it sees a row another request committed after this transaction began.
	return frappe.db.get_value(ENCOUNTER_DOCTYPE, {"pair_key": pair_key}, "name", for_update=for_update)


ENCOUNTER_FIELDS = ["name", "user_a", "user_b", "status", "raven_channel", "burn_at", "saved_by_a", "saved_by_b"]


def _require_party(encounter, statuses=("Open",)):
	"""The encounter, if the session user is one of its two people and it is in one of `statuses`.

	A saved or burned encounter no longer exists: "This chat has ended."
	"""
	doc = frappe.db.get_value(ENCOUNTER_DOCTYPE, encounter, ENCOUNTER_FIELDS, as_dict=True)
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


def _video(doc):
	"""Where the two meet on video, or None when video is off for this site."""
	switch = frappe.conf.get("chip_space_video")
	if switch is not None and not frappe.utils.cint(switch):
		return None
	domain = str(frappe.conf.get("chip_space_jitsi_domain") or JITSI_DEFAULT_DOMAIN).strip().strip("/")
	# A bare host name: the page loads https://<domain>/external_api.js from it.
	if not re.fullmatch(r"[A-Za-z0-9.-]+(:\d+)?", domain):
		return None
	room = frappe.db.get_value(ENCOUNTER_DOCTYPE, doc.name, "jitsi_room")
	if not room:
		# Encounters from before #2059 get their room on first use.
		room = _new_jitsi_room()
		frappe.db.set_value(ENCOUNTER_DOCTYPE, doc.name, "jitsi_room", room, update_modified=False)
	return {"domain": domain, "room": room}


def _new_jitsi_room():
	# Unguessable: on a public Jitsi server, whoever knows the name can walk in.
	return f"phamos-chip-{frappe.generate_hash(length=24)}"


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
	if name:
		# Met again while the burn notice ran: the chat goes on.
		_cancel_burn(_require_party(name, ("Open", "Parting")))
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
		# Both pages notice the meeting and call this at the same moment; the pair key's unique
		# index lets one insert win. The other undoes only its insert and takes the winner's.
		frappe.db.savepoint("chip_space_encounter")
		try:
			doc.insert(ignore_permissions=True)
		except (frappe.UniqueValidationError, frappe.DuplicateEntryError):
			frappe.db.rollback(save_point="chip_space_encounter")
			name = _open_encounter_name(pair_key, for_update=True)
			if not name:
				frappe.throw(_("The chat is just being opened. Please try again."))
		else:
			doc.db_set("raven_channel", _create_channel(user_a, user_b), update_modified=False)
			name = doc.name
	return _encounter_payload(_require_party(name))


@frappe.whitelist()
def get_encounter(encounter):
	"""An encounter of mine (open or parting), with its latest messages."""
	_require_user()
	return _encounter_payload(_require_party(encounter, ("Open", "Parting")))


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


def _burn(doc, silent=False):
	"""Delete the chat for good: every message the Raven way (search index, attached files,
	Raven's own events), then the channel, then the encounter."""
	if doc.raven_channel and frappe.db.exists("Raven Channel", doc.raven_channel):
		for message in frappe.get_all("Raven Message", filters={"channel_id": doc.raven_channel}, pluck="name"):
			_delete_permanently("Raven Message", message)
		_delete_permanently("Raven Channel", doc.raven_channel)
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
	doc = _require_party(encounter, ("Parting",))
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
			"phamos.api.chip_space.dummy_save", queue="short", enqueue_after_commit=True, encounter=doc.name, dummy=peer
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
		_burn(doc)
		return {"burned": True}
	return {"burned": False}


def burn_due_encounters():
	"""Scheduler, every minute: burn what is overdue, and start the countdown for encounters whose
	other person has left (tab closed, connection gone) without anyone walking away."""
	for doc in frappe.get_all(
		ENCOUNTER_DOCTYPE,
		filters={"status": "Parting", "burn_at": ("<=", now_datetime())},
		fields=ENCOUNTER_FIELDS,
	):
		_burn(doc)
	for doc in frappe.get_all(ENCOUNTER_DOCTYPE, filters={"status": "Open"}, fields=ENCOUNTER_FIELDS):
		if not (_position_of(doc.user_a) and _position_of(doc.user_b)):
			_start_parting(doc)
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
