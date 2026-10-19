# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Run an AI agent on one document: skills phase by phase, logged in an AI Agent Run.

The run executes as the agent's own user, so every value the agent writes shows up in the
document history under that user and every later human edit is a visible correction.
"""

import time

import frappe
from frappe import _
from frappe.utils import now_datetime

from phamos.ai_agents import conditions, locks
from phamos.ai_agents.context import ERROR, FAILED, PASSED, SKIPPED, UNCERTAIN, AgentContext
from phamos.ai_agents.registry import load_handler_module

PHASES = ("Extract", "Identify", "Classify", "Enrich", "Decide", "Act")
RUN_DOCTYPE = "AI Agent Run"


def get_agent(doctype):
	"""The enabled agent responsible for a document type, or None."""
	name = frappe.db.get_value("AI Agent", {"applies_to_doctype": doctype, "enabled": 1}, "name")
	return frappe.get_doc("AI Agent", name) if name else None


def enqueue_run(doctype, name, trigger="Manual", mode="Fill Empty"):
	"""Queue a run. Returns {"queued", "run", "reason"}; one run per document at a time."""
	agent = get_agent(doctype)
	if not agent:
		return {"queued": False, "reason": "no_agent"}
	if not locks.acquire(doctype, name):
		return {"queued": False, "reason": "already_running", "run": latest_run(doctype, name)}
	try:
		run = _new_run(agent, doctype, name, trigger, mode)
		frappe.enqueue(
			execute,
			queue="long",
			timeout=600,
			run_name=run.name,
			enqueue_after_commit=True,
			job_id=f"ai_agent_run::{run.name}",
		)
	except Exception:
		locks.release(doctype, name)
		raise
	return {"queued": True, "run": run.name}


def run_now(doctype, name, trigger="Manual", mode="Fill Empty"):
	"""Run synchronously (tests, debugging). Returns the finished run document."""
	agent = get_agent(doctype)
	if not agent:
		frappe.throw(_("No enabled AI Agent works on {0}.").format(doctype))
	if not locks.acquire(doctype, name):
		frappe.throw(_("An AI run for {0} is already in progress.").format(name))
	run = _new_run(agent, doctype, name, trigger, mode)
	execute(run.name, commit=False)
	return frappe.get_doc(RUN_DOCTYPE, run.name)


def latest_run(doctype, name):
	return frappe.db.get_value(
		RUN_DOCTYPE, {"reference_doctype": doctype, "reference_name": name}, "name", order_by="creation desc"
	)


def _new_run(agent, doctype, name, trigger, mode):
	run = frappe.get_doc(
		{
			"doctype": RUN_DOCTYPE,
			"agent": agent.name,
			"reference_doctype": doctype,
			"reference_name": name,
			"trigger": trigger,
			"mode": mode,
			"status": "Queued",
			"triggered_by": frappe.session.user,
		}
	)
	run.insert(ignore_permissions=True)
	return run


def execute(run_name, commit=True):
	"""Run every applicable skill of the agent on the document.

	As a background job (commit=True) the result is committed. Called synchronously the
	caller owns the transaction. A failure undoes the half-done document changes (savepoint)
	but keeps the run with its error.
	"""
	run = frappe.get_doc(RUN_DOCTYPE, run_name)
	previous_user = frappe.session.user
	started = time.monotonic()
	frappe.db.savepoint("ai_agent_run")
	try:
		agent = frappe.get_doc("AI Agent", run.agent)
		frappe.set_user(agent.user)
		doc = frappe.get_doc(run.reference_doctype, run.reference_name)
		module = load_handler_module(agent.handler_module)
		ctx = AgentContext(run=run, agent=agent, doc=doc, mode=run.mode or "Fill Empty")
		_set_party(ctx, module)
		run.db_set({"status": "Running", "started_at": now_datetime()})
		_run_phases(ctx, module)
		if hasattr(module, "finalize"):
			module.finalize(ctx)
		_finish(run, ctx, "Completed", started)
	except Exception as e:
		frappe.db.rollback(save_point="ai_agent_run")
		frappe.log_error(title=_("AI agent run {0} failed").format(run_name), message=frappe.get_traceback())
		run.reload()
		run.db_set(
			{
				"status": "Failed",
				"error": str(e)[:1000],
				"finished_at": now_datetime(),
				"duration": round(time.monotonic() - started, 2),
			}
		)
	finally:
		frappe.set_user(previous_user)
		locks.release(run.reference_doctype, run.reference_name)
		if commit:
			frappe.db.commit()
		frappe.publish_realtime(
			"ai_agent_run_update",
			{"run": run.name, "reference_doctype": run.reference_doctype, "reference_name": run.reference_name,
			 "status": run.status},
			doctype=run.reference_doctype,
			docname=run.reference_name,
		)


def _set_party(ctx, module):
	if hasattr(module, "get_party"):
		ctx.party = module.get_party(ctx.doc)


def applicable_skills(ctx, phase, with_handler=None):
	"""Enabled skills of the agent in a phase whose scope and condition match, in order.

	Skills scoped to a party apply only to documents of that party; skills without a party
	apply to all. with_handler=True/False filters on whether a code step is attached.
	"""
	skills = frappe.get_all(
		"AI Skill",
		filters={"agent": ctx.agent.name, "phase": phase, "enabled": 1},
		fields=["name", "handler", "party_doctype", "party", "condition", "order"],
		order_by="`order` asc, creation asc",
	)
	result = []
	for skill in skills:
		if skill.party and (not ctx.party or (skill.party_doctype, skill.party) != tuple(ctx.party)):
			continue
		if with_handler is True and not skill.handler:
			continue
		if with_handler is False and skill.handler:
			continue
		try:
			if not conditions.evaluate(skill.condition, ctx.eval_context()):
				continue
		except Exception as e:
			ctx.flags.append({"code": "skill_condition_error", "severity": "warn",
				"message": _("Condition of skill {0} failed: {1}").format(skill.name, e)})
			continue
		result.append(skill)
	return result


def prompt_rules(ctx, phase):
	"""Enabled prompt rules of all applicable skills of a phase: general skills first, then
	the ones for this party, each sorted by its own order."""
	skills = applicable_skills(ctx, phase)
	skills.sort(key=lambda s: (1 if s.party else 0, s.order or 0))
	rules = []
	for skill in skills:
		rows = frappe.get_all(
			"AI Prompt Rule",
			filters={"parent": skill.name, "parenttype": "AI Skill", "enabled": 1},
			fields=["case_description", "action"],
			order_by="`order` asc, idx asc",
		)
		rules.extend(rows)
	return rules


def _run_phases(ctx, module):
	handlers = getattr(module, "SKILLS", {})
	phase_passed = {}
	for phase in PHASES:
		ctx.run.db_set("phase", phase, update_modified=False)
		statuses = []
		for skill_row in applicable_skills(ctx, phase, with_handler=True):
			skill = frappe.get_doc("AI Skill", skill_row.name)
			step = {"skill": skill.name, "skill_name": skill.skill_name, "phase": phase, "started_at": str(now_datetime())}
			if skill.gate_on_previous and not all(phase_passed.get(p, True) for p in PHASES[: PHASES.index(phase)]):
				step.update(status=SKIPPED, message=_("Skipped: an earlier phase did not pass."))
				ctx.steps.append(step)
				continue
			handler = handlers.get(skill.handler)
			if not handler:
				step.update(status=ERROR, message=_("Unknown handler {0}").format(skill.handler))
				ctx.steps.append(step)
				statuses.append(ERROR)
				continue
			try:
				result = handler(ctx, skill)
			except Exception as e:
				frappe.log_error(title=_("AI skill {0} failed").format(skill.name), message=frappe.get_traceback())
				result = None
				step.update(status=ERROR, message=str(e)[:500])
			if result is not None:
				status = result.status
				if status == PASSED and skill.min_confidence and (result.confidence or 0) < skill.min_confidence:
					status = UNCERTAIN
				step.update(status=status, confidence=result.confidence, message=result.message,
					fields_set=result.fields_set, output=result.output)
				ctx.flags.extend(result.flags)
				ctx.fields_set.extend(f for f in result.fields_set if f not in ctx.fields_set)
			step["finished_at"] = str(now_datetime())
			ctx.steps.append(step)
			statuses.append(step["status"])
			if step["status"] in (FAILED, UNCERTAIN, ERROR) and skill.on_fail == "Stop Run":
				phase_passed[phase] = False
				return
		phase_passed[phase] = all(s in (PASSED, SKIPPED) for s in statuses)


def _finish(run, ctx, status, started):
	run.reload()
	run.update(
		{
			"status": status,
			"summary": ctx.summary,
			"decision": ctx.decision,
			"confidence": ctx.confidence,
			"fields_set": ", ".join(ctx.fields_set),
			"run_flags": frappe.as_json(ctx.flags),
			"steps": frappe.as_json(ctx.steps),
			"analysis": frappe.as_json(ctx.analysis),
			"finished_at": now_datetime(),
			"duration": round(time.monotonic() - started, 2),
			"llm_model": ctx.llm_model,
			"llm_calls": ctx.llm_calls,
		}
	)
	run.save(ignore_permissions=True)
