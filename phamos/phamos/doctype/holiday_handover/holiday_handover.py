# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class HolidayHandover(Document):
	def validate(self):
		"""Validate the Holiday Handover document before saving."""
		self.validate_required_fields()
	
	def validate_required_fields(self):
		"""Ensure all mandatory fields are filled."""
		if not self.implementation:
			frappe.throw(_("Implementation is mandatory"))
		
		if not self.acting_project_manager:
			frappe.throw(_("Acting Project Manager is mandatory"))
		
		if not self.overview or not self.overview.strip():
			frappe.throw(_("Overview / Implementation Status is mandatory"))
		
		if not self.critical_tasks or not self.critical_tasks.strip():
			frappe.throw(_("Critical Tasks / Notes is mandatory"))
	



def get_permission_query_conditions(user):
	"""
	Permission query to restrict Holiday Handover access.
	Only the Account Manager of the Implementation can create/edit.
	Acting PM and others can read based on Project permissions.
	"""
	if not user:
		user = frappe.session.user
	
	# System Manager and Projects Manager have full access
	if "System Manager" in frappe.get_roles(user) or "Projects Manager" in frappe.get_roles(user):
		return None
	
	# Get all Implementations where the user is the Account Manager
	implementations = frappe.db.get_all(
		"Implementation",
		filters={"account_manager": user},
		pluck="name"
	)
	
	# Get all Holiday Handovers where user is Acting PM
	acting_handovers = frappe.db.get_all(
		"Holiday Handover",
		filters={"acting_project_manager": user},
		pluck="name"
	)
	
	conditions = []
	
	if implementations:
		conditions.append(f"`tabHoliday Handover`.`implementation` in ({', '.join(['%s'] * len(implementations))})")
	
	if acting_handovers:
		conditions.append(f"`tabHoliday Handover`.`name` in ({', '.join(['%s'] * len(acting_handovers))})")
	
	if conditions:
		return " OR ".join(conditions)
	
	# No access
	return "1=0"


def has_permission(doc, ptype, user):
	"""
	Permission check for Holiday Handover.
	- Create/Write: Only Account Manager of the Implementation
	- Read: Account Manager, Acting PM, or users with Project permissions
	"""
	if not user:
		user = frappe.session.user
	
	# System Manager and Projects Manager have full access
	if "System Manager" in frappe.get_roles(user) or "Projects Manager" in frappe.get_roles(user):
		return True
	
	# Acting PM can read
	if ptype == "read" and doc.acting_project_manager == user:
		return True
	
	# Check if user is Account Manager of the Implementation
	if doc.implementation:
		account_manager = frappe.db.get_value(
			"Implementation",
			doc.implementation,
			"account_manager"
		)
		
		if account_manager == user:
			return True
	
	return False
