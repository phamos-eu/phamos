# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Chip Space (#2053): colleagues as avatar chips on a grid.

Slice 1 (#2054) keeps the user's own chip: where it stands, saved as a user default so it is
back in the same spot after a reload, in any browser. No DocType, nothing to migrate.

Positions are in tile units but not whole tiles: the grid is drawn, movement is free.

Dummy chips for testing (until presence, #2055, shows the real people online) come from the
site config, so they never appear on a site that does not set them:

	"chip_space_dummies": [{"user": "chip-buddy@example.com", "x": 24, "y": 12}]
"""

import json
import math

import frappe
from frappe import _

# One shared world for everyone; the frontend draws exactly this grid.
COLS = 40
ROWS = 25
POSITION_KEY = "phamos_chip_space_position"
DUMMIES_CONF_KEY = "chip_space_dummies"
MAX_DUMMIES = 10


def _require_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to use the Space."), frappe.PermissionError)


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


@frappe.whitelist()
def get_space():
	"""The grid size, my chip (where it stands, or the spawn) and the other chips."""
	_require_user()
	user = frappe.session.user
	return {
		"cols": COLS,
		"rows": ROWS,
		"me": {**_chip(user, _stored_position() or _spawn()), "cols": COLS, "rows": ROWS},
		"others": _dummies(user),
	}


@frappe.whitelist(methods=["POST"])
def save_my_position(x, y):
	"""Remember where my chip stands; values outside the grid are moved onto its edge."""
	_require_user()
	position = {"x": _clamp(x, COLS), "y": _clamp(y, ROWS)}
	frappe.defaults.set_user_default(POSITION_KEY, json.dumps(position, separators=(",", ":")))
	return position
