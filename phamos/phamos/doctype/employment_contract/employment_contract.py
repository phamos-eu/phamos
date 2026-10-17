# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Working time (FTE) and pay agreed with a person, valid for a date range.

Every change is a new submitted record. Submitting a record closes the open-ended
record before it, so at most one contract applies to an employee on any given day.
Capacity code should read contracts through ``get_active_contract``, which never
returns salary fields.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, get_link_to_form, getdate, nowdate

OPEN_END = "9999-12-31"
CAPACITY_FIELDS = (
	"name",
	"employee",
	"contract_type",
	"effective_from",
	"valid_until",
	"fte_percentage",
	"full_time_hours_per_week",
	"weekly_hours",
)


class EmploymentContract(Document):
	def validate(self):
		self.validate_dates()
		self.validate_fte()
		self.calculate_amounts()
		self.validate_expense_account()
		self.validate_no_overlap()
		self.status = compute_status(self.docstatus, self.effective_from, self.valid_until)

	def on_submit(self):
		self.supersede_open_predecessor()
		self.db_set("status", compute_status(1, self.effective_from, self.valid_until))

	def on_cancel(self):
		self.db_set("status", "Cancelled")
		# The continuation links back to this record, so it goes first; otherwise the
		# restored predecessor would stop where the continuation starts.
		self.cancel_continuations()
		self.restore_superseded()

	def validate_dates(self):
		if self.valid_until and getdate(self.valid_until) < getdate(self.effective_from):
			frappe.throw(_("Valid Until cannot be before Effective From."))

		relieving_date = frappe.db.get_value("Employee", self.employee, "relieving_date")
		if not relieving_date:
			return
		if getdate(self.effective_from) > getdate(relieving_date):
			frappe.throw(_("Effective From is after the employee's relieving date {0}.").format(frappe.format(relieving_date, "Date")))
		if not self.valid_until:
			self.valid_until = relieving_date
		elif getdate(self.valid_until) > getdate(relieving_date):
			frappe.throw(_("Valid Until is after the employee's relieving date {0}.").format(frappe.format(relieving_date, "Date")))

	def validate_fte(self):
		if not 0 < flt(self.fte_percentage) <= 100:
			frappe.throw(_("FTE % must be greater than 0 and at most 100."))
		if flt(self.full_time_hours_per_week) <= 0:
			frappe.throw(_("Full-Time Hours per Week must be greater than 0."))

	def calculate_amounts(self):
		"""Recompute derived values on the server; the client-side values are only a preview."""
		self.weekly_hours = flt(flt(self.fte_percentage) * flt(self.full_time_hours_per_week) / 100, self.precision("weekly_hours"))

		if self.contract_type == "External":
			if flt(self.monthly_amount) <= 0:
				frappe.throw(_("Enter the Agreed Monthly Amount for an external contract."))
			self.yearly_gross_full_time = 0
			self.monthly_gross = flt(self.monthly_amount, self.precision("monthly_gross"))
		else:
			if flt(self.yearly_gross_full_time) <= 0:
				frappe.throw(_("Enter the Yearly Gross at 100 % FTE for an employed contract."))
			self.monthly_amount = 0
			self.monthly_gross = flt(
				flt(self.yearly_gross_full_time) * flt(self.fte_percentage) / 100 / 12,
				self.precision("monthly_gross"),
			)

	def validate_expense_account(self):
		if not self.expense_account:
			return
		account = frappe.db.get_value("Account", self.expense_account, ["company", "root_type", "is_group"], as_dict=True)
		if account.company != self.company or account.root_type != "Expense" or account.is_group:
			frappe.throw(
				_("Expense Account {0} must be a non-group Expense account of company {1}.").format(
					frappe.bold(self.expense_account), frappe.bold(self.company)
				)
			)

	def validate_no_overlap(self):
		"""No two submitted contracts of one employee may cover the same day.

		An open-ended contract that starts earlier is not a conflict: submitting this
		record closes it the day before this one starts.
		"""
		contract = frappe.qb.DocType("Employment Contract")
		my_end = self.valid_until or OPEN_END
		conflicts = (
			frappe.qb.from_(contract)
			.select(contract.name, contract.effective_from, contract.valid_until)
			.where(contract.employee == self.employee)
			.where(contract.docstatus == 1)
			.where(contract.name != (self.name or ""))
			.where(contract.effective_from <= my_end)
			.where(frappe.query_builder.functions.IfNull(contract.valid_until, OPEN_END) >= self.effective_from)
			.where(~(contract.valid_until.isnull() & (contract.effective_from < self.effective_from)))
			.limit(1)
		).run(as_dict=True)

		if conflicts:
			other = conflicts[0]
			frappe.throw(
				_("This contract overlaps with {0} ({1} to {2}).").format(
					get_link_to_form("Employment Contract", other.name),
					frappe.format(other.effective_from, "Date"),
					frappe.format(other.valid_until, "Date") if other.valid_until else _("open end"),
				),
				title=_("Overlapping Contract"),
			)

	def supersede_open_predecessor(self):
		predecessors = frappe.get_all(
			"Employment Contract",
			filters={
				"employee": self.employee,
				"docstatus": 1,
				"valid_until": ("is", "not set"),
				"effective_from": ("<", self.effective_from),
				"name": ("!=", self.name),
			},
			pluck="name",
		)
		for name in predecessors:
			close_contract(name, add_days(self.effective_from, -1), superseded_by=self.name)
			if self.valid_until:
				self.continue_after_temporary_change(name)

	def continue_after_temporary_change(self, predecessor):
		"""Resume the open-ended terms once a fixed-term change ends.

		A temporary change (e.g. part-time from March to April) replaces an open-ended
		contract only for its own period. Without a continuation the employee would have
		no contract after Valid Until, and capacity and cost would drop to zero.
		"""
		start = add_days(self.valid_until, 1)
		relieving_date = frappe.db.get_value("Employee", self.employee, "relieving_date")
		if relieving_date and getdate(start) > getdate(relieving_date):
			return

		continuation = frappe.copy_doc(frappe.get_doc("Employment Contract", predecessor))
		continuation.update(
			{
				"effective_from": start,
				"valid_until": None,
				"continuation_of": self.name,
				"notes": _("Continues {0} after the temporary change {1}.").format(predecessor, self.name),
			}
		)
		continuation.insert()
		continuation.submit()
		frappe.msgprint(
			_("{0} resumes the earlier terms from {1}.").format(
				get_link_to_form("Employment Contract", continuation.name), frappe.format(start, "Date")
			),
			alert=True,
		)

	def cancel_continuations(self):
		for name in frappe.get_all(
			"Employment Contract", filters={"continuation_of": self.name, "docstatus": 1}, pluck="name"
		):
			frappe.get_doc("Employment Contract", name).cancel()

	def restore_superseded(self):
		"""Undo what submitting this record did to the contract it superseded.

		If a later contract still exists, the old one runs until that one starts;
		otherwise it becomes open-ended again.
		"""
		for name in frappe.get_all("Employment Contract", filters={"superseded_by": self.name}, pluck="name"):
			effective_from = frappe.db.get_value("Employment Contract", name, "effective_from")
			following = frappe.get_all(
				"Employment Contract",
				filters={
					"employee": self.employee,
					"docstatus": 1,
					"effective_from": (">", effective_from),
					"name": ("!=", self.name),
				},
				fields=["name", "effective_from"],
				order_by="effective_from asc",
				limit=1,
			)
			if following:
				close_contract(name, add_days(following[0].effective_from, -1), superseded_by=following[0].name)
			else:
				close_contract(name, None, superseded_by=None)


def close_contract(name, valid_until, superseded_by):
	effective_from = frappe.db.get_value("Employment Contract", name, "effective_from")
	frappe.db.set_value(
		"Employment Contract",
		name,
		{
			"valid_until": valid_until,
			"superseded_by": superseded_by,
			"status": compute_status(1, effective_from, valid_until),
		},
	)
	if superseded_by:
		frappe.get_doc("Employment Contract", name).add_comment(
			"Info", _("Superseded by {0}.").format(get_link_to_form("Employment Contract", superseded_by))
		)


def compute_status(docstatus, effective_from, valid_until, on_date=None):
	if docstatus == 0:
		return "Draft"
	if docstatus == 2:
		return "Cancelled"
	today = getdate(on_date or nowdate())
	if getdate(effective_from) > today:
		return "Upcoming"
	if valid_until and getdate(valid_until) < today:
		return "Expired"
	return "Active"


def get_active_contract(employee, on_date=None):
	"""Return the capacity fields of the contract that applies on ``on_date``, or None.

	Reads without permission checks so capacity code works for every user; salary
	fields are deliberately not part of the result.
	"""
	on_date = getdate(on_date or nowdate())
	contracts = frappe.get_all(
		"Employment Contract",
		filters={
			"employee": employee,
			"docstatus": 1,
			"effective_from": ("<=", on_date),
		},
		fields=list(CAPACITY_FIELDS),
		order_by="effective_from desc",
		limit=1,
	)
	if not contracts:
		return None
	contract = contracts[0]
	if contract.valid_until and getdate(contract.valid_until) < on_date:
		return None
	return contract


def update_contract_statuses():
	"""Daily job: move contracts between Upcoming, Active and Expired as dates pass."""
	for contract in frappe.get_all(
		"Employment Contract",
		filters={"docstatus": 1, "status": ("in", ["Upcoming", "Active"])},
		fields=["name", "status", "effective_from", "valid_until"],
	):
		status = compute_status(1, contract.effective_from, contract.valid_until)
		if status != contract.status:
			frappe.db.set_value("Employment Contract", contract.name, "status", status, update_modified=False)


HISTORY_FIELDS = (
	"name",
	"docstatus",
	"status",
	"contract_type",
	"effective_from",
	"valid_until",
	"fte_percentage",
	"weekly_hours",
	"monthly_gross",
	"currency",
)


@frappe.whitelist()
def get_contract_history(employee):
	"""All draft and submitted contracts of one employee, newest first."""
	frappe.has_permission("Employment Contract", "read", throw=True)
	return frappe.get_list(
		"Employment Contract",
		filters={"employee": employee, "docstatus": ("<", 2)},
		fields=list(HISTORY_FIELDS),
		order_by="effective_from desc, creation desc",
	)


def cap_contracts_at_relieving_date(employee, method=None):
	"""Employee on_update: end open contracts on the relieving date.

	Leaving is recorded on the Employee, not on the contract. Without this, a leaver's
	open-ended contract would stay Active and keep counting towards FTE and cost.
	Runs for whoever saves the Employee (often an HR User without contract access), so
	it writes with db.set_value; it only ever shortens contracts, never extends them.
	"""
	if not employee.relieving_date:
		return
	relieving_date = getdate(employee.relieving_date)
	contracts = frappe.get_all(
		"Employment Contract",
		filters={"employee": employee.name, "docstatus": 1},
		fields=["name", "effective_from", "valid_until"],
	)
	for contract in contracts:
		if getdate(contract.effective_from) > relieving_date:
			frappe.msgprint(
				_("{0} starts after the relieving date. Cancel it if it no longer applies.").format(
					get_link_to_form("Employment Contract", contract.name)
				),
				indicator="orange",
				alert=True,
			)
			continue
		if contract.valid_until and getdate(contract.valid_until) <= relieving_date:
			continue
		frappe.db.set_value(
			"Employment Contract",
			contract.name,
			{
				"valid_until": relieving_date,
				"status": compute_status(1, contract.effective_from, relieving_date),
			},
		)
		frappe.get_doc("Employment Contract", contract.name).add_comment(
			"Info", _("Ended on the employee's relieving date {0}.").format(frappe.format(relieving_date, "Date"))
		)
