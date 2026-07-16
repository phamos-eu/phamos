# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


DEFAULT_BOT_OPTIONS = (
	("a", "Send a welcome email with our standard marketing materials", "Send Welcome Email", "✅ Welcome email sent."),
	("b", "Suggest an appointment", "Suggest Appointment", "✅ Appointment suggested."),
	("c", "Add to the general newsletter", "Add to Newsletter", "✅ Added to newsletter."),
	("d", "All of the options above", "All Actions", "✅ All actions completed."),
)


class RavenBotSetting(Document):
	def validate(self):
		existing_keys = {
			(row.option_key or "").strip().lower()
			for row in self.get("table_npdu", [])
		}

		for key, label, action, response in DEFAULT_BOT_OPTIONS:
			if key in existing_keys:
				continue
			self.append("table_npdu", {
				"option_key": key,
				"option_label": label,
				"action_type": action,
				"response_message": response,
				"is_enabled": 1,
			})


def ensure_default_bot_options():
	"""Repair a setting created when only some default option rows existed."""
	settings = frappe.get_single("Raven Bot Setting")
	settings.save(ignore_permissions=True)
	return [row.option_key for row in settings.get("table_npdu", [])]
