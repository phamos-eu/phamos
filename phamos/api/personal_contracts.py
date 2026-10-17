# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""My own Employment Contracts in the Personal Cockpit (phamos/phamos#1600).

Employment Contract stays readable only for HR Manager in Desk. Employees see their own
contracts through this module instead: it resolves the session user's Employee on the
server and reads only that employee's submitted contracts, so no role permission on the
doctype is needed and nobody can ask for someone else's contract.
"""

import frappe
from frappe.utils import getdate, nowdate

from phamos.cockpits.workdays import _employee

# What an employee may see of their own contract. Expense account and HR notes stay internal.
FIELDS = (
	"name",
	"status",
	"contract_type",
	"effective_from",
	"valid_until",
	"fte_percentage",
	"full_time_hours_per_week",
	"weekly_hours",
	"currency",
	"yearly_gross_full_time",
	"monthly_amount",
	"monthly_gross",
)


def get_my_contracts():
	"""The session user's contracts: the one in force today, upcoming ones and the full history."""
	employee = _employee(frappe.session.user)
	if not employee:
		return {"employee": None, "current": None, "upcoming": [], "history": []}

	# ignore permissions on purpose: the filter on the user's own Employee is the access check.
	history = frappe.get_all(
		"Employment Contract",
		filters={"employee": employee, "docstatus": 1},
		fields=list(FIELDS),
		order_by="effective_from desc",
	)
	today = getdate(nowdate())
	current = next(
		(
			c
			for c in history
			if getdate(c.effective_from) <= today and (not c.valid_until or getdate(c.valid_until) >= today)
		),
		None,
	)
	upcoming = sorted((c for c in history if getdate(c.effective_from) > today), key=lambda c: c.effective_from)
	return {
		"employee": employee,
		"employee_name": frappe.db.get_value("Employee", employee, "employee_name"),
		"current": current,
		"upcoming": upcoming,
		"history": history,
	}
