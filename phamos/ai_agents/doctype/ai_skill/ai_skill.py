# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AISkill(Document):
	def validate(self):
		if self.party and not self.party_doctype:
			frappe.throw(_("Set the party type for the party {0}.").format(self.party))
		if self.handler:
			from phamos.ai_agents.registry import get_handlers

			handlers = get_handlers(self.agent)
			if self.handler not in handlers:
				frappe.throw(
					_("Unknown handler {0}. The agent offers: {1}").format(self.handler, ", ".join(sorted(handlers)))
				)
		if self.condition:
			from phamos.ai_agents.conditions import validate_expression

			validate_expression(self.condition)
