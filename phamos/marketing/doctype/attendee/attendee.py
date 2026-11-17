# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""One person at one event: guest, speaker, sponsor, employee, ...

Participation (``status``) and money (``payment_status``) are kept apart: who is coming is one
question, who has paid another. ``payment_status`` and the order links are maintained by
``phamos.marketing.billing`` from the Quotation, Sales Order and Sales Invoice.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from phamos.marketing.defaults import CONSENT_FIELDS, FREE_TICKET_TYPES, ROLES_WITHOUT_TICKET
from phamos.marketing.utils import join_name, normalize_email


class Attendee(Document):
	def before_insert(self):
		if not self.registered_on:
			self.registered_on = now_datetime()
		if self.payment_status in (None, "", "Pending") and (
			self.role in ROLES_WITHOUT_TICKET or self.ticket_type in FREE_TICKET_TYPES
		):
			self.payment_status = "Not Required"

	def validate(self):
		self.email = normalize_email(self.email) if (self.email or "").strip() else None
		self.first_name = (self.first_name or "").strip()
		self.last_name = (self.last_name or "").strip()
		self.full_name = join_name(self.first_name, self.last_name)
		self.stamp_consents()
		self.stamp_check_in()
		self.check_duplicate()

	def on_update(self):
		# The order's status follows its tickets (phamos/phamos#1723).
		if self.event_ticket_order and (self.has_value_changed("status") or self.has_value_changed("payment_status")
				or self.is_new()):
			from phamos.marketing.doctype.event_ticket_order.event_ticket_order import refresh_status

			refresh_status(self.event_ticket_order)

	def stamp_consents(self):
		now = now_datetime()
		for field in CONSENT_FIELDS:
			if self.get(field) and not self.get(f"{field}_on"):
				self.set(f"{field}_on", now)
			elif not self.get(field):
				self.set(f"{field}_on", None)

	def stamp_check_in(self):
		if self.status in ("Attended", "No Show") and not self.checked_in_on and self.has_value_changed("status"):
			self.checked_in_on = now_datetime()
			self.checked_in_by = frappe.session.user if frappe.session.user != "Guest" else None

	def check_duplicate(self):
		if self.status == "Cancelled" or not self.email:
			return
		other = frappe.db.get_value("Attendee", {
			"event": self.event,
			"email": self.email,
			"status": ["!=", "Cancelled"],
			"name": ["!=", self.name or ""],
		})
		if other:
			frappe.throw(
				_("{0} is already registered for this event ({1}).").format(self.email, other),
				frappe.DuplicateEntryError,
			)
