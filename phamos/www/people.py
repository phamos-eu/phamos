# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	people = frappe.get_all(
		"Website Person",
		filters={"published": 1},
		fields=["name", "full_name", "position", "department", "years_at_phamos", "photo", "short_bio"],
		order_by="sort_order asc",
	)

	positions = sorted({p.position for p in people if p.position})
	departments = sorted({p.department for p in people if p.department})
	max_years = max([p.years_at_phamos or 0 for p in people], default=0)

	context.people = people
	context.title = _("People")
	context.parents = [{"title": _("Home"), "route": "/"}]
	context.filter_facets = [
		{"key": "position", "label": _("Position"), "options": positions},
		{"key": "department", "label": _("Department"), "options": departments},
		{
			"key": "years",
			"label": _("Years at phamos"),
			"type": "range",
			"options": [
				{"value": "0-1", "label": _("< 2 Jahre")},
				{"value": "2-4", "label": _("2 - 4 Jahre")},
				{"value": "5-99", "label": _("5+ Jahre")},
			],
		},
	]
