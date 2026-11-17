# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Settings of the cockpits, one tab per cockpit (#1932). They lived in phamos Settings before."""

import frappe
from frappe.model.document import Document

# Privacy mode of the HR Cockpit (#1839): shorter than this and the data is gone before it can be read.
MIN_PRIVACY_REVEAL_SECONDS = 10


class CockpitSettings(Document):
	def validate(self):
		seconds = self.human_resources_privacy_reveal_seconds
		if seconds is not None and seconds < MIN_PRIVACY_REVEAL_SECONDS:
			frappe.throw(
				frappe._("Privacy mode must show data for at least {0} seconds.").format(MIN_PRIVACY_REVEAL_SECONDS)
			)
