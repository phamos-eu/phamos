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

# route -> (field prefix in Cockpit Settings, logo colour). The colours are the app icon tiles of
# spa_shared/scripts/generate_app_manifests.py; they are the defaults of the <prefix>_color fields.
COCKPITS = {
	"/human-resources-cockpit": ("human_resources", "#be123c"),
	"/sales-cockpit": ("sales", "#c2410c"),
	"/accounting-cockpit": ("accounting", "#047857"),
	"/project-management-cockpit": ("project_management", "#6d28d9"),
	"/software-development-cockpit": ("software_development", "#334155"),
	"/personal-cockpit": ("personal", "#0e7490"),
}

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def cockpit_window(route):
	"""Window colour and edge glow of the cockpit at `route`, for its boot and page (#1933).

	Returns:
		dict: color ("#rrggbb", or None for a neutral title bar and no glow) and glow (one of
		GLOW_MODES). Anything else stored in the fields counts as no colour / glow off.
	"""
	prefix = COCKPITS.get(route, (None,))[0]
	if not prefix:
		return {"color": None, "glow": GLOW_OFF}
	color = (frappe.db.get_single_value(COCKPIT_SETTINGS, f"{prefix}_color") or "").strip()
	glow = frappe.db.get_single_value(COCKPIT_SETTINGS, f"{prefix}_glow")
	color = color.lower() if _HEX_COLOR.match(color) else None
	return {"color": color, "glow": glow if color and glow in GLOW_MODES else GLOW_OFF}
