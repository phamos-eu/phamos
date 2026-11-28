# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Cockpit Settings (#1932): the Single that holds the per-cockpit settings, and the window colour
and edge glow each cockpit reads from it (#1933)."""

import re

import frappe

COCKPIT_SETTINGS = "Cockpit Settings"

# Window title bar (theme-color) when a cockpit has no colour: the page background, as before #1933.
NEUTRAL_THEME_COLOR = "#f8f8f8"

GLOW_OFF = "Off"
GLOW_MODES = (GLOW_OFF, "Always", "On focus", "Always + on focus")
# Window edges the glow can come from, each a Check <prefix>_glow_<edge>; right and bottom by default.
GLOW_EDGES = ("top", "left", "bottom", "right")
DEFAULT_GLOW_EDGES = ("bottom", "right")

# route -> (field prefix in Cockpit Settings, logo colour). The colours are the app icon tiles of
# spa_shared/scripts/generate_app_manifests.py; they are the defaults of the <prefix>_color fields.
COCKPITS = {
	"/human-resources-cockpit": ("human_resources", "#be123c"),
	"/sales-cockpit": ("sales", "#c2410c"),
	"/accounting-cockpit": ("accounting", "#047857"),
	"/project-management-cockpit": ("project_management", "#6d28d9"),
	"/software-development-cockpit": ("software_development", "#334155"),
	"/general-management-cockpit": ("general_management", "#a16207"),
	"/implementation-cockpit": ("implementation", "#0f766e"),
	"/personal-cockpit": ("personal", "#0e7490"),
}

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def cockpit_window(route):
	"""Window colour and edge glow of the cockpit at `route`, for its boot and page (#1933).

	Returns:
		dict: color ("#rrggbb", or None for a neutral title bar and no glow), glow (one of
		GLOW_MODES), edges (the GLOW_EDGES switched on, in that order) and breathing (bool).
		Anything else stored in the fields counts as no colour / glow off; no edge switched on
		means glow off.
	"""
	off = {"color": None, "glow": GLOW_OFF, "edges": [], "breathing": False}
	prefix = COCKPITS.get(route, (None,))[0]
	if not prefix:
		return off
	color = (frappe.db.get_single_value(COCKPIT_SETTINGS, f"{prefix}_color") or "").strip()
	if not _HEX_COLOR.match(color):
		return off
	glow = frappe.db.get_single_value(COCKPIT_SETTINGS, f"{prefix}_glow")
	edges = [
		edge for edge in GLOW_EDGES if frappe.db.get_single_value(COCKPIT_SETTINGS, f"{prefix}_glow_{edge}")
	]
	if glow not in GLOW_MODES or not edges or glow == GLOW_OFF:
		return {**off, "color": color.lower()}
	breathing = bool(frappe.db.get_single_value(COCKPIT_SETTINGS, f"{prefix}_glow_breathing"))
	return {"color": color.lower(), "glow": glow, "edges": edges, "breathing": breathing}
