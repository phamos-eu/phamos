# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Per-user cockpit preferences (#1910).

Stored as Frappe user defaults, so a preference follows the user across browsers and cockpits
instead of living in one browser's localStorage. Only the keys listed in PREFERENCES can be read
or written, each with its own validator: the values arrive from the browser and end up in
tabDefaultValue.
"""

import json

import frappe
from frappe import _

# One stored layout must stay small: it is sent with every cockpit page load (spa_boot).
MAX_LAYOUT_BYTES = 8000
MAX_PANELS_PER_DOCTYPE = 30
MIN_DOCK_WIDTH = 240
MAX_DOCK_WIDTH = 1600


def _clean_ids(value):
	"""A list of short panel ids, without duplicates, order kept."""
	if not isinstance(value, list):
		return []
	ids = []
	for item in value[:MAX_PANELS_PER_DOCTYPE]:
		if isinstance(item, str) and 0 < len(item) <= 64 and item not in ids:
			ids.append(item)
	return ids


def _clean_panel_layout(value):
	"""{doctype: {order: [ids], collapsed: [ids], expanded: [ids], width: int}}; anything else is dropped.

	Unknown panel ids are kept: whether a panel still exists is decided in the browser by the
	registry, which ignores ids it does not know (a cockpit may not have every panel).
	"""
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			frappe.throw(_("The panel layout is not valid JSON."))
	if not isinstance(value, dict):
		frappe.throw(_("The panel layout must be an object."))

	clean = {}
	for doctype, layout in list(value.items())[:MAX_PANELS_PER_DOCTYPE]:
		if not isinstance(doctype, str) or not doctype or len(doctype) > 140 or not isinstance(layout, dict):
			continue
		# collapsed / expanded hold only the panels the user switched away from their default
		entry = {
			"order": _clean_ids(layout.get("order")),
			"collapsed": _clean_ids(layout.get("collapsed")),
			"expanded": _clean_ids(layout.get("expanded")),
		}
		width = layout.get("width")
		if isinstance(width, (int, float)) and not isinstance(width, bool):
			entry["width"] = int(min(max(width, MIN_DOCK_WIDTH), MAX_DOCK_WIDTH))
		clean[doctype] = entry

	if len(json.dumps(clean)) > MAX_LAYOUT_BYTES:
		frappe.throw(_("The panel layout is too large."))
	return clean


# key -> (validator returning the value to store, value when nothing is stored)
PREFERENCES = {
	"cockpit_panel_layout": (_clean_panel_layout, {}),
}


def get_preferences(user=None):
	"""All known preferences of `user` (default: the session user), decoded.

	Called by spa_boot for every cockpit page load, so the dock needs no request of its own.
	"""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return {}
	values = {}
	for key, (_validate, default) in PREFERENCES.items():
		raw = frappe.defaults.get_user_default(key, user=user)
		if raw in (None, ""):
			values[key] = default
			continue
		try:
			values[key] = json.loads(raw)
		except ValueError:
			# a hand-edited or truncated value must not break the cockpit boot
			values[key] = default
	return values


@frappe.whitelist(methods=["POST"])
def set_preference(key, value=None):
	"""Store one preference for the session user. An empty value resets it to the default."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Log in to save preferences."), frappe.PermissionError)
	if key not in PREFERENCES:
		frappe.throw(_("Unknown preference: {0}").format(key))

	validate, default = PREFERENCES[key]
	if value in (None, "", "null"):
		frappe.defaults.clear_user_default(key)
		return default

	clean = validate(value)
	frappe.defaults.set_user_default(key, json.dumps(clean, separators=(",", ":")))
	return clean
