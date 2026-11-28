# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Ophice's background image becomes the world (phamos/phamos#2139).

The image used to be placed on the grid ("layout", in squares). Now the grid is placed on the
image ("grid", in image widths), and zoom 1 shows the whole image instead of the whole grid.
This stores the converted placement and starting zoom, so every map looks as before. The old
"layout" stays in the value; it is dropped the next time a map editor changes the placement.
"""

import json

import frappe

from phamos.api.ophice import BACKGROUND_KEY, _background, _grid_on_image


def execute():
	value = _background()
	if not value.get("url") or isinstance(value.get("grid"), dict):
		return
	value["grid"], value["zoom"] = _grid_on_image(value)
	frappe.db.set_default(BACKGROUND_KEY, json.dumps(value, separators=(",", ":")))
