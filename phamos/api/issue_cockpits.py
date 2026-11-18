# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Which cockpits can show an Issue: the "Open in Cockpit" group on the Desk form (#1957).

A cockpit fits when the session user can open it and the Issue is in its scope, by the
same rules the cockpit's own Issue detail page uses (department_cockpit._issue_in_scope).
"""

from urllib.parse import quote

import frappe
from frappe import _

from phamos.api import department_cockpit as dc

# Best fit first: the Personal Cockpit, then the Issue's own department, then its project's.
RANK_PERSONAL = 0
RANK_ISSUE_DEPARTMENT = 1
RANK_PROJECT_DEPARTMENT = 2


def _cockpit_modules():
	"""(module, route) of every cockpit on the Apps screen with a CockpitConfig, in hooks order."""
	cockpits = []
	for app in frappe.get_hooks("add_to_apps_screen", app_name="phamos"):
		try:
			module = frappe.get_module(f"phamos.api.{app['name']}")
		except ImportError:
			continue
		if isinstance(getattr(module, "CONFIG", None), dc.CockpitConfig):
			cockpits.append((module, app["route"]))
	return cockpits


def _rank(config, doc):
	if config.is_personal:
		return RANK_PERSONAL
	if doc.get("custom_department") and doc.custom_department == dc._get_department(config):
		return RANK_ISSUE_DEPARTMENT
	return RANK_PROJECT_DEPARTMENT


def _short_label(config):
	# "Personal Cockpit" → "Personal": the group label already says "Cockpit".
	return config.label.removesuffix(" Cockpit")


def cockpits_for_issue(doc):
	"""Fitting cockpits for an Issue doc as [{label, url}], best fit first."""
	found = []
	for position, (module, route) in enumerate(_cockpit_modules()):
		config = module.CONFIG
		if not module.check_app_permission() or not dc._issue_in_scope(config, doc):
			continue
		found.append(
			(
				_rank(config, doc),
				position,
				{
					"label": _(_short_label(config)),
					"url": f"{route}/issues/list/{quote(doc.name, safe='')}",
				},
			)
		)
	return [entry for _rank_, _position, entry in sorted(found, key=lambda row: row[:2])]


@frappe.whitelist()
def get_issue_cockpits(name):
	"""Cockpits that can show this Issue, for the Desk form's "Open in Cockpit" group."""
	doc = frappe.get_doc("Issue", name)
	doc.check_permission("read")
	return cockpits_for_issue(doc)
