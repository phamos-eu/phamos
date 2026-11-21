# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Chip Space (#2053): colleagues as avatar chips on a grid.

Slice 1 (#2054) keeps only the user's own chip: where it stands, saved as a user default so it
is back in the same spot after a reload, in any browser. No DocType, nothing to migrate.
"""

import json

import frappe
from frappe import _

# One shared world for everyone; the frontend draws exactly this grid.
COLS = 40
ROWS = 25
POSITION_KEY = "phamos_chip_space_position"


def _require_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to use the Space."), frappe.PermissionError)


def _clamp(value, upper):
	"""An int inside 0..upper-1; anything that is not a number counts as 0."""
	try:
		value = int(value)
	except (TypeError, ValueError):
		value = 0
	return max(0, min(upper - 1, value))


def _spawn():
	return {"x": COLS // 2, "y": ROWS // 2}


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


@frappe.whitelist()
def get_my_position():
	"""My chip: where it stands (or the spawn tile), the grid size and how it looks."""
	_require_user()
	user = frappe.session.user
	full_name, user_image = frappe.db.get_value("User", user, ["full_name", "user_image"]) or ("", "")
	return {
		**(_stored_position() or _spawn()),
		"cols": COLS,
		"rows": ROWS,
		"user": user,
		"full_name": full_name or user,
		"user_image": user_image or "",
	}


@frappe.whitelist(methods=["POST"])
def save_my_position(x, y):
	"""Remember where my chip stands; values outside the grid are moved onto its edge."""
	_require_user()
	position = {"x": _clamp(x, COLS), "y": _clamp(y, ROWS)}
	frappe.defaults.set_user_default(POSITION_KEY, json.dumps(position, separators=(",", ":")))
	return position
