# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

""""Covered by" on Leave Application (phamos/phamos#1714, Q6).

`custom_cover_employee` names the colleague who covers during the leave. The leave
auto-reply (Phase 6 of docs/mailcow-calendar-plan.md) will reuse it for the reply text.
"""

import frappe
from frappe import _

COVER_FIELD = "custom_cover_employee"


def validate_cover(doc, method=None):
	"""Leave Application validate: nobody covers for themselves."""
	cover = doc.get(COVER_FIELD)
	if cover and cover == doc.employee:
		frappe.throw(_("You cannot cover for yourself."))
