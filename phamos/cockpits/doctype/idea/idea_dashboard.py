# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from frappe import _


def get_data():
	"""Connections tab of the Idea form: the ideas that grew out of this one (spawned_from), as
	linked in the Personal Cockpit or the Idea Catcher's "Grew out of it" (#2200). The idea this one
	grew out of is the "Spawned From" field itself."""
	return {
		"fieldname": "spawned_from",
		"transactions": [{"label": _("Grew out of this idea"), "items": ["Idea"]}],
	}
