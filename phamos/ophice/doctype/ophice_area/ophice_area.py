# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""A space of the Ophice map (phamos/phamos#2060). Logic lives in phamos.api.ophice."""

import frappe
from frappe import _
from frappe.model.document import Document


class OphiceArea(Document):
	def validate(self):
		# Every page in the space loads https://<jitsi_domain>/external_api.js into the site's own
		# origin. The API only accepts trusted servers; this keeps an edit in Desk to the same list
		# (review of the release).
		if not self.jitsi_domain:
			return
		from phamos.api.ophice import _allowed_jitsi_domains

		if self.jitsi_domain.strip().lower() not in _allowed_jitsi_domains():
			frappe.throw(
				_("Only meetings on {0} can be used here.").format(", ".join(sorted(_allowed_jitsi_domains())))
			)
