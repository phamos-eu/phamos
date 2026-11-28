# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Skill handlers live in code, one module per agent, as SKILLS = {"name": function}.

A handler takes the AgentContext and returns a SkillResult. Agents decide in the UI which
skills run, when, for whom and with which prompt rules; the code only does the work.
"""

import importlib

import frappe


def load_handler_module(path):
	return importlib.import_module(path)


@frappe.whitelist()
def get_handlers(agent):
	"""Names of the handlers an agent offers (for the AI Skill form)."""
	frappe.has_permission("AI Agent", "read", doc=agent, throw=True)
	return handlers_of(agent)


def handlers_of(agent):
	"""Names of the handlers an agent offers, without a permission check (server-side validation: a suggestion
	is saved in the session of the person whose correction made it, #2225)."""
	module_path = frappe.db.get_value("AI Agent", agent, "handler_module")
	if not module_path:
		return {}
	module = load_handler_module(module_path)
	return {name: (fn.__doc__ or "").strip().split("\n")[0] for name, fn in getattr(module, "SKILLS", {}).items()}
