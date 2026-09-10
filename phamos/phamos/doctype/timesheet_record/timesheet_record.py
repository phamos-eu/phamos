# Copyright (c) 2023, Phamos GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (cstr, now_datetime, time_diff_in_seconds, get_datetime, flt, nowdate, get_first_day, get_last_day, get_url_to_form,)

class TimesheetRecord(Document):

	def before_insert(self):
		self.check_implementation_time_limit_fully_used()

	def before_submit(self):
		if not self.to_time:
			frappe.throw(_("Cannot Submit, please mark record as complete"))
		if not self.activity_type:
			frappe.throw(_("Please add an activity type to submit the timesheet record."))

		self.check_implementation_time_limit()

		try:
			if self.to_time:
				to_dt = get_datetime(self.to_time)
				creation_dt = get_datetime(self.creation)

				if to_dt.date() != creation_dt.date():
					self.timesheet_record_color = "Red"
				else:
					duration = (creation_dt - to_dt).total_seconds() / 3600
					if duration < 1:
						self.timesheet_record_color = "Green"
					else:
						self.timesheet_record_color = "Amber"
		except Exception as e:
			frappe.msgprint(f"Color coding failed: {e}")


	def on_submit(self):
		self.create_timesheet()
		self.sync_implementation_time_limit_summary()

	def on_cancel(self):
		self.delete_timesheet()
		self.sync_implementation_time_limit_summary()

	def get_billable_hours(self):
		if not self.actual_time or not self.percent_billable or self.percent_billable == "0":
			return 0.0
		return (flt(self.actual_time) / 3600) * (flt(self.percent_billable) / 100)

	def check_implementation_time_limit(self):
		implementation_name = self.get_implementation()
		if not implementation_name:
			return

		implementation = frappe.db.get_value(
			"Implementation",
			implementation_name,
			[
				"enable_time_limit",
				"recurring_monthly",
				"time_limit_from_date",
				"time_limit_to_date",
				"limit_hours",
				"enforce_limit",
				"warning_threshold_percent",
				"account_manager",
			],
			as_dict=True,
		)
		if not implementation or not implementation.enable_time_limit:
			return

		from_date, to_date = get_time_limit_period(implementation)
		if not from_date or not to_date:
			return

		limit_hours = flt(implementation.limit_hours)
		if not limit_hours:
			return

		used_hours = get_billable_hours_in_period_for_implementation(implementation_name, from_date, to_date)
		total_hours = used_hours + self.get_billable_hours()

		percent = round(total_hours / limit_hours * 100, 1)
		remaining_hours_before = max(limit_hours - used_hours, 0)

		if implementation.enforce_limit and total_hours > limit_hours:
			is_account_manager = bool(implementation.account_manager) and frappe.session.user == implementation.account_manager

			if is_account_manager:
				frappe.msgprint(
					_(
						"Only {0}h were available out of the {1}h time limit for {2} to {3}, but this record "
						"takes total billable hours to {4}h. Submitting anyway since you are the account "
						"manager for this implementation."
					).format(round(remaining_hours_before, 2), limit_hours, from_date, to_date, round(total_hours, 2)),
					indicator="orange",
					alert=True,
				)
			else:
				frappe.throw(
					_(
						"Cannot submit: only {0}h are still available out of the {1}h time limit for {2} to "
						"{3}, and this record would exceed it. The account manager has been notified and only "
						"they can submit it."
					).format(
						round(remaining_hours_before, 2),
						limit_hours,
						from_date,
						to_date,
					)
				)

		if implementation.warning_threshold_percent:
			threshold_hours = limit_hours * flt(implementation.warning_threshold_percent) / 100
			if total_hours >= threshold_hours:
				frappe.msgprint(
					_(
						"Implementation {0} has now used {1}h of its {2}h time limit for {3} to {4} ({5}%)."
					).format(
						implementation_name,
						round(total_hours, 2),
						limit_hours,
						from_date,
						to_date,
						percent,
					),
					indicator="orange",
					alert=True,
				)
				notify_account_manager_of_time_limit(
					implementation_name,
					implementation.account_manager,
					_("Time limit warning: Implementation {0} at {1}%").format(implementation_name, percent),
					_(
						"Implementation {0} has now used {1}h of its {2}h time limit for {3} to {4} ({5}%)."
					).format(implementation_name, round(total_hours, 2), limit_hours, from_date, to_date, percent),
				)

	def check_implementation_time_limit_fully_used(self):
		implementation_name = self.get_implementation()
		if not implementation_name:
			return

		implementation = frappe.db.get_value(
			"Implementation",
			implementation_name,
			[
				"enable_time_limit",
				"recurring_monthly",
				"time_limit_from_date",
				"time_limit_to_date",
				"limit_hours",
				"enforce_limit",
			],
			as_dict=True,
		)
		if not implementation or not implementation.enable_time_limit or not implementation.enforce_limit:
			return

		from_date, to_date = get_time_limit_period(implementation)
		if not from_date or not to_date:
			return

		limit_hours = flt(implementation.limit_hours)
		if not limit_hours:
			return

		used_hours = get_billable_hours_in_period_for_implementation(implementation_name, from_date, to_date)
		if used_hours >= limit_hours:
			frappe.throw(
				_(
					"Cannot create a new timesheet record: Implementation {0} has already used its full time "
					"limit of {1}h for the period {2} to {3}."
				).format(implementation_name, limit_hours, from_date, to_date)
			)

	def get_implementation(self):
		if not self.project:
			return None
		return frappe.db.get_value("Project", self.project, "custom_implementation")

	def sync_implementation_time_limit_summary(self):
		implementation_name = self.get_implementation()
		if implementation_name:
			update_implementation_time_limit_summary(implementation_name)

	def delete_timesheet(self):
		docstatus = frappe.db.get_value('Timesheet',self.timesheet,'docstatus')
		if docstatus == 0:
			frappe.db.set_value("Timesheet Record", self.name, "timesheet", '')
			frappe.delete_doc('Timesheet',self.timesheet)
			frappe.msgprint(_('Timesheet {0} deleted successfully').format(self.timesheet))
			self.reload()
		elif docstatus == 1:
			frappe.throw(_('The timesheet {0} linked to record {1} has already been submitted and cannot be canceled.').format(self.timesheet, self.name))

	def create_timesheet(self):
		description = "{0} : {1}".format(self.goal, self.result)
		actual_hours = round(float(self.actual_time) / 3600, 6)

		child_url = frappe.db.get_value("GitLab Issue", self.gitlab_issue, "issue_url") if self.gitlab_issue else None
		parent_url = frappe.db.get_value("GitLab Issue", self.gitlab_parent_issue, "issue_url") if self.gitlab_parent_issue else child_url

		timesheet = frappe.new_doc("Timesheet")
		timesheet.update(
			{
				"parent_project": self.project,
				"customer": self.customer,
				"note": description,
				"employee": self.employee,
				"custom_gitlab_child_issue_url": child_url,
				"custom_gitlab_parent_issue_url": parent_url,
			}
		)
		timesheet.append(
			"time_logs",
			{
				"is_billable": 1 if self.percent_billable!="0" else 0,
				"billing_hours": actual_hours * (float(self.percent_billable) / 100) if self.percent_billable!="0" else 0,
				"activity_type": self.activity_type,
				"from_time": self.from_time,
				"to_time": self.to_time,
				"expected_hours": round(float(self.expected_time) / 3600, 6),
				"hours": actual_hours,
				"description": description,
				"project": self.project,
				"task": self.task,
			},
		)
		timesheet.insert()
		self.db_set('timesheet', timesheet.name)

		# frappe.msgprint(_('Timesheet {0} Created').format(frappe.get_desk_link("Timesheet", timesheet.name)))

@frappe.whitelist()
def set_actual_time(from_time, to_time):
	if from_time and to_time:
		return time_diff_in_seconds(to_time, from_time)


def notify_account_manager_of_time_limit(implementation_name, account_manager, subject, message):
	if not account_manager:
		return
	account_manager_email = frappe.db.get_value("User", account_manager, "email") or account_manager
	try:
		frappe.sendmail(recipients=[account_manager_email], subject=subject, message=message)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Implementation time limit notification failed")


def get_enforced_time_limit_details(implementation_name):
	"""Returns implementation time-limit fields, or None if the limit doesn't apply/isn't enforced."""
	implementation = frappe.db.get_value(
		"Implementation",
		implementation_name,
		[
			"enable_time_limit",
			"recurring_monthly",
			"time_limit_from_date",
			"time_limit_to_date",
			"limit_hours",
			"enforce_limit",
			"account_manager",
		],
		as_dict=True,
	)
	if not implementation or not implementation.enable_time_limit or not implementation.enforce_limit:
		return None

	from_date, to_date = get_time_limit_period(implementation)
	if not from_date or not to_date:
		return None

	limit_hours = flt(implementation.limit_hours)
	if not limit_hours:
		return None

	implementation.from_date = from_date
	implementation.to_date = to_date
	implementation.limit_hours = limit_hours
	return implementation


def compute_time_limit_status(doc):
	"""Checks an in-memory Timesheet Record doc (already updated, not necessarily saved yet)
	against its implementation's time limit, without throwing. Used both by the whitelisted
	get_time_limit_status (desk form submit) and directly by other submit entry points (e.g.
	the Project Action Panel's Stop button) that build up the doc themselves before saving."""
	implementation_name = doc.get_implementation()
	if not implementation_name:
		return {"exceeds": False}

	details = get_enforced_time_limit_details(implementation_name)
	if not details:
		return {"exceeds": False}

	used_hours = get_billable_hours_in_period_for_implementation(
		implementation_name, details.from_date, details.to_date
	)
	requested_hours = doc.get_billable_hours()
	total_hours = used_hours + requested_hours
	remaining_hours = max(details.limit_hours - used_hours, 0)

	is_account_manager = bool(details.account_manager) and frappe.session.user == details.account_manager

	return {
		"exceeds": total_hours > details.limit_hours and not is_account_manager,
		"remaining_hours": remaining_hours,
		"requested_hours": requested_hours,
		"limit_hours": details.limit_hours,
		"from_date": details.from_date,
		"to_date": details.to_date,
	}


@frappe.whitelist()
def get_time_limit_status(name):
	"""Called from the client before submitting, to decide whether to show the
	cancel-and-notify-PM message instead of submitting straight away."""
	doc = frappe.get_doc("Timesheet Record", name)
	return compute_time_limit_status(doc)


@frappe.whitelist()
def notify_pm_of_time_limit(name):
	"""Emails the implementation's account manager with the hours the employee wants to submit,
	how many are actually available, and the to-time they logged, so the account manager has an
	idea before deciding whether to submit it themselves."""
	doc = frappe.get_doc("Timesheet Record", name)
	implementation_name = doc.get_implementation()
	if not implementation_name:
		frappe.throw(_("No implementation linked to this record."))

	details = get_enforced_time_limit_details(implementation_name)
	if not details:
		frappe.throw(_("This record is not over any time limit."))

	if not details.account_manager:
		frappe.throw(_("No account manager is set on this implementation to notify."))

	used_hours = get_billable_hours_in_period_for_implementation(
		implementation_name, details.from_date, details.to_date
	)
	remaining_hours = max(details.limit_hours - used_hours, 0)
	requested_hours = doc.get_billable_hours()
	record_url = get_url_to_form("Timesheet Record", doc.name)

	notify_account_manager_of_time_limit(
		implementation_name,
		details.account_manager,
		_("Approval needed: {0}h timesheet submission for {1}").format(round(requested_hours, 2), doc.project),
		_(
			"{0} wants to submit {1}h billable for Project {2} (to time: {3}), but only {4}h are still "
			"available out of the {5}h time limit for {6} to {7}. Only you, as the account manager, can "
			"submit this record as requested.<br><br>"
			"<a href=\"{8}\">Open Timesheet Record {9}</a>"
		).format(
			doc.employee or frappe.session.user,
			round(requested_hours, 2),
			doc.project,
			doc.to_time,
			round(remaining_hours, 2),
			details.limit_hours,
			details.from_date,
			details.to_date,
			record_url,
			doc.name,
		),
	)

	return {"remaining_hours": remaining_hours, "requested_hours": requested_hours}


@frappe.whitelist()
def submit_at_available_hours(name):
	"""Keeps the employee's logged from/to time exactly as entered, and only lowers the billable
	percentage (to the highest of the standard 0/25/50/75/100 tiers that still fits) so the
	billable hours don't exceed what's available under the implementation's time limit."""
	doc = frappe.get_doc("Timesheet Record", name)
	implementation_name = doc.get_implementation()
	if not implementation_name:
		frappe.throw(_("No implementation linked to this record."))

	details = get_enforced_time_limit_details(implementation_name)
	if not details:
		frappe.throw(_("This record is not over any time limit; please submit it normally."))

	actual_hours = flt(doc.actual_time) / 3600
	if not actual_hours:
		frappe.throw(_("Cannot adjust hours: no actual time is logged on this record."))

	used_hours = get_billable_hours_in_period_for_implementation(
		implementation_name, details.from_date, details.to_date
	)
	remaining_hours = max(details.limit_hours - used_hours, 0)
	original_percent_billable = doc.percent_billable

	new_percent_billable = 0
	for option in (0, 25, 50, 75, 100):
		if actual_hours * (option / 100) <= remaining_hours:
			new_percent_billable = option

	doc.add_comment(
		"Info",
		_(
			"Percent billable reduced from {0}% to {1}% to fit the {2}h time limit for {3} to {4}. "
			"From/To Time were kept exactly as logged."
		).format(
			original_percent_billable,
			new_percent_billable,
			details.limit_hours,
			details.from_date,
			details.to_date,
		),
	)

	doc.percent_billable = cstr(new_percent_billable)
	doc.docstatus = 0
	doc.save()
	doc.submit()
	return {"percent_billable": doc.percent_billable}


def get_time_limit_period(implementation):
	"""Returns (from_date, to_date) for the implementation's current time-limit period.

	If the implementation repeats every calendar month, the period is always
	today's month, computed on the fly. Otherwise it is the fixed date range
	set on the implementation (e.g. for a one-off trial phase).
	"""
	if implementation.recurring_monthly:
		today = nowdate()
		return get_first_day(today), get_last_day(today)
	return implementation.time_limit_from_date, implementation.time_limit_to_date


def get_billable_hours_in_period_for_implementation(implementation_name, from_date, to_date):
	projects = frappe.get_all(
		"Project", filters={"custom_implementation": implementation_name}, pluck="name"
	)
	if not projects:
		return 0.0

	rows = frappe.get_all(
		"Timesheet Record",
		filters={
			"project": ["in", projects],
			"docstatus": 1,
			"from_time": ["between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]],
		},
		fields=["actual_time", "percent_billable"],
	)
	total_hours = 0.0
	for row in rows:
		if not row.actual_time or not row.percent_billable or row.percent_billable == "0":
			continue
		total_hours += (flt(row.actual_time) / 3600) * (flt(row.percent_billable) / 100)
	return total_hours


def update_implementation_time_limit_summary(implementation_name):
	implementation = frappe.db.get_value(
		"Implementation",
		implementation_name,
		[
			"enable_time_limit",
			"recurring_monthly",
			"time_limit_from_date",
			"time_limit_to_date",
			"limit_hours",
		],
		as_dict=True,
	)
	if not implementation:
		return

	if not implementation.enable_time_limit:
		frappe.db.set_value(
			"Implementation",
			implementation_name,
			{
				"hours_used_this_period": 0,
				"remaining_hours": 0,
				"time_limit_percent_used": 0,
			},
		)
		return

	from_date, to_date = get_time_limit_period(implementation)
	if not from_date or not to_date:
		return

	used_hours = get_billable_hours_in_period_for_implementation(implementation_name, from_date, to_date)
	limit_hours = flt(implementation.limit_hours)
	remaining_hours = (limit_hours - used_hours) if limit_hours else 0.0
	percent_used = (used_hours / limit_hours * 100) if limit_hours else 0.0

	frappe.db.set_value(
		"Implementation",
		implementation_name,
		{
			"hours_used_this_period": used_hours,
			"remaining_hours": remaining_hours,
			"time_limit_percent_used": percent_used,
		},
	)


def sync_implementation_time_limit_summary_on_save(doc, method=None):
	update_implementation_time_limit_summary(doc.name)


def sync_implementation_time_limit_summary_from_project(doc, method=None):
	if doc.custom_implementation:
		update_implementation_time_limit_summary(doc.custom_implementation)
