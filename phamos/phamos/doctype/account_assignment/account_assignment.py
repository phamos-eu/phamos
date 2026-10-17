# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from phamos.accounting.library import VALIDATION_RANK, normalize_description

MANAGER_ROLES = {"System Manager", "Accounts Manager"}


class AccountAssignment(Document):
	def validate(self):
		self.pattern = normalize_description(self.sample_description)
		if not self.pattern:
			frappe.throw(_("The sample description has no words left to match on."))
		self.validate_account()
		self.validate_unique()
		self.validate_validation_change()

	def validate_account(self):
		from phamos.accounting.expense_accounts import is_expense_account

		if not is_expense_account(self.expense_account, self.company):
			frappe.throw(_("{0} is not an expense account of {1}.").format(self.expense_account, self.company))

	def validate_unique(self):
		duplicate = frappe.db.get_value(
			"Account Assignment",
			{
				"company": self.company,
				"supplier": self.supplier or ("is", "not set"),
				"pattern": self.pattern,
				"expense_account": self.expense_account,
				"name": ("!=", self.name or ""),
			},
			"name",
		)
		if duplicate:
			frappe.throw(_("{0} already assigns this description to {1}.").format(duplicate, self.expense_account))

	def validate_validation_change(self):
		"""Validation only moves up, except for accounting managers. Moving up records who and when."""
		before = self.get_doc_before_save()
		old = before.validation if before else None
		if old == self.validation:
			return
		if old and VALIDATION_RANK[self.validation] < VALIDATION_RANK[old] and not (set(frappe.get_roles()) & MANAGER_ROLES):
			frappe.throw(_("Only an Accounts Manager can lower the validation of an entry."))
		if self.validation != "AI":
			self.validated_by = frappe.session.user
			self.validated_at = now_datetime()
