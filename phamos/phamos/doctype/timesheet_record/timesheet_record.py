# Copyright (c) 2023, Phamos GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, now_datetime, time_diff_in_seconds, get_datetime

class TimesheetRecord(Document):

	def before_submit(self):
		if not self.to_time:
			frappe.throw(_("Cannot Submit, please mark record as complete"))
		if not self.activity_type:
			frappe.throw(_("Please add an activity type to submit the timesheet record."))

	def on_submit(self):
		self.create_timesheet()

	def create_timesheet(self):
		description = "{0} : {1}".format(self.goal, self.result)
		actual_hours = round(float(self.actual_time) / 3600, 6)
		timesheet = frappe.new_doc("Timesheet")
		timesheet.update(
			{
				"project": self.project,
				"customer": self.customer,
				"note": description,
				"employee": self.employee
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
				"task": self.task
			},
		)
		timesheet.insert()
		self.db_set('timesheet', timesheet.name)
		
		frappe.msgprint(_('Make sure to provide the issue number, chat link from Mattermost, and your solution. Note that this information will be shared with the customer via the timesheet record.<br><br>Timesheet {0} Created').format(frappe.get_desk_link("Timesheet", timesheet.name)))

@frappe.whitelist()
def set_actual_time(from_time, to_time):
	if from_time and to_time:
		return time_diff_in_seconds(to_time, from_time)
