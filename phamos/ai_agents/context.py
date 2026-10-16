# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from dataclasses import dataclass, field

import frappe
from frappe.utils import nowdate

PASSED, FAILED, UNCERTAIN, SKIPPED, ERROR = "Passed", "Failed", "Uncertain", "Skipped", "Error"


@dataclass
class SkillResult:
	status: str = PASSED
	confidence: float | None = None  # 0..100
	message: str = ""
	fields_set: list = field(default_factory=list)
	flags: list = field(default_factory=list)  # [{code, severity: block|warn|info, message, field?}]
	output: dict = field(default_factory=dict)


@dataclass
class AgentContext:
	run: object
	agent: object
	doc: object
	mode: str = "Fill Empty"
	party: tuple | None = None  # (doctype, name)
	analysis: dict = field(default_factory=dict)
	flags: list = field(default_factory=list)
	fields_set: list = field(default_factory=list)
	steps: list = field(default_factory=list)
	llm_calls: int = 0
	llm_model: str | None = None
	summary: str = ""
	decision: str | None = None
	confidence: float | None = None

	@property
	def overwrite(self):
		return self.mode == "Overwrite"

	def eval_context(self):
		return {
			"doc": self.doc,
			"party": frappe._dict(doctype=self.party[0], name=self.party[1]) if self.party else None,
			"analysis": frappe._dict(self.analysis),
			"flags": self.flags,
			"nowdate": nowdate,
			"frappe": frappe._dict(utils=frappe.utils),
		}
