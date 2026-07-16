# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from frappe.model.document import Document


DEFAULT_BOT_OPTIONS = (
	("a", "Send a welcome email with our standard marketing materials", "Send Welcome Email", "✅ Welcome email sent."),
	("b", "Suggest an appointment", "Suggest Appointment", "✅ Appointment suggested."),
	("c", "Add to the general newsletter", "Add to Newsletter", "✅ Added to newsletter."),
	("d", "All of the options above", "All Actions", "✅ All actions completed."),
)


class RavenBotSetting(Document):
	def validate(self):
		if self.get("table_npdu"):
			return

		for key, label, action, response in DEFAULT_BOT_OPTIONS:
			self.append("table_npdu", {
				"option_key": key,
				"option_label": label,
				"action_type": action,
				"response_message": response,
				"is_enabled": 1,
			})
