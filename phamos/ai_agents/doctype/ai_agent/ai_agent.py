# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AIAgent(Document):
	def validate(self):
		from phamos.ai_agents.registry import load_handler_module

		try:
			load_handler_module(self.handler_module)
		except Exception:
			frappe.throw(_("Handler module {0} cannot be imported.").format(self.handler_module))
