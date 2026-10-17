# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Cockpit API for AI agents: their skills, settings, dry runs and run history.

Doctype-scoped (an agent works on one doctype), so other cockpits can reuse it."""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_datetime, now_datetime

from phamos.ai_agents.registry import load_handler_module

SKILL_EDITABLE = ("skill_name", "enabled", "order", "on_fail", "min_confidence", "description")
RULE_FIELDS = ("enabled", "order", "case_description", "action", "reason")
STATS_DAYS = 30


def _agent(doctype):
	name = frappe.db.get_value("AI Agent", {"applies_to_doctype": doctype}, "name", order_by="enabled desc")
	if not name:
		frappe.throw(_("No AI Agent works on {0}.").format(doctype))
	return frappe.get_doc("AI Agent", name)


def _module(agent):
	return load_handler_module(agent.handler_module)


def _parse(value, default):
	if value in (None, ""):
		return default
	return json.loads(value) if isinstance(value, str) else value


def _skill_stats(agent_name, days=STATS_DAYS):
	"""{skill: {runs, Passed, Uncertain, Failed, Error, Skipped}} over the last `days`."""
	rows = frappe.get_all(
		"AI Agent Run",
		filters={"agent": agent_name, "creation": (">=", add_days(now_datetime(), -days))},
		fields=["steps"],
		limit_page_length=2000,
	)
	stats = {}
	for row in rows:
		for step in _parse(row.steps, []) or []:
			entry = stats.setdefault(step.get("skill"), {"runs": 0})
			entry["runs"] += 1
			status = step.get("status") or "Unknown"
			entry[status] = entry.get(status, 0) + 1
	return stats


@frappe.whitelist(methods=["POST"])
def get_ai_skills(doctype="Accounting Receipt"):
	"""The agent of a doctype with its skills (by phase) and 30-day step counts."""
	frappe.has_permission("AI Skill", "read", throw=True)
	agent = _agent(doctype)
	stats = _skill_stats(agent.name)
	skills = frappe.get_all(
		"AI Skill",
		filters={"agent": agent.name},
		fields=["name", "skill_name", "phase", "order", "enabled", "handler", "party_doctype", "party", "origin",
			"description", "modified"],
		order_by="`order` asc, creation asc",
	)
	for skill in skills:
		skill["stats"] = stats.get(skill.name, {"runs": 0})
	from phamos.ai_agents.runner import PHASES

	return {
		"agent": {"name": agent.name, "enabled": agent.enabled, "user": agent.user, "llm_model": agent.llm_model},
		"phases": list(PHASES),
		"skills": skills,
		"stats_days": STATS_DAYS,
		"can_write": 1 if frappe.has_permission("AI Skill", "write") else 0,
	}


@frappe.whitelist(methods=["POST"])
def get_ai_skill(name):
	"""One skill for the editor: settings, params with their form fields, prompt rules."""
	skill = frappe.get_doc("AI Skill", name)
	skill.check_permission("read")
	agent = frappe.get_doc("AI Agent", skill.agent)
	module = _module(agent)
	fields, defaults = module.param_fields(skill.handler) if hasattr(module, "param_fields") else ([], {})
	return {
		"name": skill.name,
		"skill_name": skill.skill_name,
		"agent": skill.agent,
		"phase": skill.phase,
		"order": skill.order,
		"enabled": skill.enabled,
		"handler": skill.handler,
		"party_doctype": skill.party_doctype,
		"party": skill.party,
		"condition": skill.condition,
		"on_fail": skill.on_fail,
		"on_fail_options": [o for o in (frappe.get_meta("AI Skill").get_field("on_fail").options or "").split("\n") if o],
		"min_confidence": skill.min_confidence,
		"description": skill.description,
		"origin": skill.origin,
		"params": {**defaults, **(_parse(skill.params, {}) or {})},
		"param_fields": fields,
		"prompt_rules": [{f: row.get(f) for f in ("name",) + RULE_FIELDS} for row in skill.prompt_rules],
		"has_dry_run": 1 if skill.handler in ("extract_document", "classify_lines", "decide_receipt") else 0,
		"modified": str(skill.modified),
		"can_write": 1 if skill.has_permission("write") else 0,
	}


def _clean_params(fields, params):
	"""Keep the known params, coerced to their type and range."""
	clean = dict(params or {})
	for field in fields:
		key = field["key"]
		if key not in clean:
			continue
		if field["type"] == "check":
			clean[key] = 1 if cint(clean[key]) else 0
		elif field["type"] == "int":
			value = cint(clean[key])
			if "min" in field and value < field["min"] or "max" in field and value > field["max"]:
				frappe.throw(_("{0} must be between {1} and {2}.").format(_(field["label"]), field.get("min"), field.get("max")))
			clean[key] = value
	return clean


@frappe.whitelist(methods=["POST"])
def save_ai_skill(name, values, modified=None):
	"""Save the editor: settings, params and prompt rules. A stale `modified` is refused."""
	values = _parse(values, {})
	skill = frappe.get_doc("AI Skill", name)
	skill.check_permission("write")
	if modified and get_datetime(modified) != get_datetime(skill.modified):
		frappe.throw(_("Someone else changed this skill meanwhile. Reload it and try again."), frappe.TimestampMismatchError)
	for field in SKILL_EDITABLE:
		if field in values:
			skill.set(field, values[field])
	if "params" in values:
		module = _module(frappe.get_doc("AI Agent", skill.agent))
		fields, _defaults = module.param_fields(skill.handler) if hasattr(module, "param_fields") else ([], {})
		skill.params = frappe.as_json(_clean_params(fields, _parse(values["params"], {})))
	if "prompt_rules" in values:
		skill.set("prompt_rules", [])
		for i, row in enumerate(_parse(values["prompt_rules"], []) or [], 1):
			if not (row.get("case_description") or row.get("action")):
				continue
			skill.append("prompt_rules", {"enabled": 1 if row.get("enabled", 1) else 0, "order": cint(row.get("order")) or i,
				"case_description": row.get("case_description"), "action": row.get("action"), "reason": row.get("reason")})
	skill.save()
	return get_ai_skill(name)


@frappe.whitelist(methods=["POST"])
def set_skill_enabled(name, enabled):
	skill = frappe.get_doc("AI Skill", name)
	skill.check_permission("write")
	skill.enabled = 1 if cint(enabled) else 0
	skill.save()
	return {"name": skill.name, "enabled": skill.enabled}


@frappe.whitelist(methods=["POST"])
def dry_run_ai_skill(skill, reference_name, params=None, prompt_rules=None):
	"""Run a skill's logic with draft settings on one document; nothing is saved."""
	skill_doc = frappe.get_doc("AI Skill", skill)
	skill_doc.check_permission("read")
	agent = frappe.get_doc("AI Agent", skill_doc.agent)
	doc = frappe.get_doc(agent.applies_to_doctype, reference_name)
	doc.check_permission("read")
	module = _module(agent)
	if not hasattr(module, "dry_run"):
		frappe.throw(_("This agent has no dry run."))
	fields, defaults = module.param_fields(skill_doc.handler) if hasattr(module, "param_fields") else ([], {})
	draft_params = {**defaults, **(_parse(skill_doc.params, {}) or {}), **_clean_params(fields, _parse(params, {}))}
	rules = _parse(prompt_rules, None)
	if rules is None:
		rules = [{f: r.get(f) for f in RULE_FIELDS} for r in skill_doc.prompt_rules]
	frappe.db.savepoint("ai_skill_dry_run")
	try:
		return module.dry_run(skill_doc.handler, doc, draft_params, rules)
	finally:
		frappe.db.rollback(save_point="ai_skill_dry_run")


@frappe.whitelist(methods=["POST"])
def get_agent_runs(doctype="Accounting Receipt", status=None, reference_name=None, limit=50):
	"""Recent runs of the agent, newest first."""
	frappe.has_permission("AI Agent Run", "read", throw=True)
	agent = _agent(doctype)
	filters = {"agent": agent.name}
	if status:
		filters["status"] = status
	if reference_name:
		filters["reference_name"] = reference_name
	rows = frappe.get_all(
		"AI Agent Run",
		filters=filters,
		fields=["name", "reference_doctype", "reference_name", "status", "trigger", "mode", "decision", "confidence",
			"summary", "duration", "llm_calls", "llm_model", "run_flags", "error", "creation", "triggered_by"],
		order_by="creation desc",
		limit_page_length=min(cint(limit) or 50, 200),
	)
	for row in rows:
		flags = _parse(row.pop("run_flags"), []) or []
		row["flag_count"] = sum(1 for f in flags if f.get("severity") in ("warn", "block"))
		row["creation"] = str(row.creation)
	return rows


@frappe.whitelist(methods=["POST"])
def get_agent_run(name):
	"""One run with its steps and flags."""
	run = frappe.get_doc("AI Agent Run", name)
	run.check_permission("read")
	analysis = _parse(run.analysis, {}) or {}
	return {
		"name": run.name,
		"reference_doctype": run.reference_doctype,
		"reference_name": run.reference_name,
		"status": run.status,
		"trigger": run.trigger,
		"mode": run.mode,
		"decision": run.decision,
		"confidence": run.confidence,
		"summary": run.summary,
		"error": run.error,
		"duration": run.duration,
		"llm_model": run.llm_model,
		"llm_calls": run.llm_calls,
		"fields_set": run.fields_set,
		"creation": str(run.creation),
		"steps": _parse(run.steps, []) or [],
		"flags": _parse(run.run_flags, []) or [],
		"classification": analysis.get("classification") or [],
	}
