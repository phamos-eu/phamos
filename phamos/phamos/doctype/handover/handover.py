# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Handover(Document):
	def validate(self):
		"""Validate the Handover document before saving."""
		self.validate_required_fields()
		self.validate_acting_project_manager()
		self.validate_gitlab_issues()

	def validate_required_fields(self):
		"""Ensure all mandatory fields are filled."""
		if not self.implementation:
			frappe.throw(_("Implementation is mandatory"))

		if not self.acting_project_manager:
			frappe.throw(_("Acting Project Manager is mandatory"))

		if not self.gitlab_project:
			frappe.throw(_("GitLab Project is mandatory"))

		if not self.overview or not self.overview.strip():
			frappe.throw(_("Overview / Implementation Status is mandatory"))

	def validate_acting_project_manager(self):
		"""Ensure Acting Project Manager is not the same as Project Manager."""
		if self.project_manager and self.acting_project_manager:
			if self.project_manager == self.acting_project_manager:
				frappe.throw(
					_("Acting Project Manager cannot be the same as Project Manager (Handover By)")
				)

	def validate_gitlab_issues(self):
		"""Validate that all selected GitLab Issues belong to the selected GitLab Project."""
		if not self.gitlab_project or not self.issues:
			return

		for row in self.issues:
			if row.gitlab_issue_id:
				# Check if the GitLab Issue belongs to the selected GitLab Project
				gitlab_issue_project = frappe.db.get_value(
					"GitLab Issue",
					row.gitlab_issue_id,
					"gitlab_project"
				)

				if gitlab_issue_project != self.gitlab_project:
					frappe.throw(
						_("GitLab Issue {0} does not belong to the selected GitLab Project {1}").format(
							frappe.bold(row.gitlab_issue_id),
							frappe.bold(self.gitlab_project)
						)
					)




def get_permission_query_conditions(user):
	"""
	Permission query to restrict Handover access.
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

	# Get all Handovers where user is Acting PM
	acting_handovers = frappe.db.get_all(
		"Handover",
		filters={"acting_project_manager": user},
		pluck="name"
	)

	conditions = []

	if implementations:
		conditions.append(f"`tabHandover`.`implementation` in ({', '.join(['%s'] * len(implementations))})")

	if acting_handovers:
		conditions.append(f"`tabHandover`.`name` in ({', '.join(['%s'] * len(acting_handovers))})")

	if conditions:
		return " OR ".join(conditions)

	# No access
	return "1=0"


def has_permission(doc, ptype, user):
	"""
	Permission check for Handover.
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
