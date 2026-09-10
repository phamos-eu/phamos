// Copyright (c) 2023, Phamos GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on('Timesheet Record', {
	before_submit: function(frm) {
		return new Promise((resolve) => {
			frappe.call({
				method: "phamos.phamos.doctype.timesheet_record.timesheet_record.get_time_limit_status",
				args: { name: frm.doc.name },
				callback: function(r) {
					let status = r.message || {};
					if (!status.exceeds) {
						resolve();
						return;
					}

					frappe.validated = false;

					frappe.msgprint({
						title: __("Time Limit Reached"),
						indicator: "red",
						message: __(
							"Only {0}h are available out of the {1}h time limit for {2} to {3}, but this record is for {4}h billable.",
							[
								flt(status.remaining_hours).toFixed(2),
								status.limit_hours,
								status.from_date,
								status.to_date,
								flt(status.requested_hours).toFixed(2),
							]
						),
						primary_action: {
							label: __("Continue with Available Hours"),
							action: () => {
								frappe.call({
									method: "phamos.phamos.doctype.timesheet_record.timesheet_record.submit_at_available_hours",
									args: { name: frm.doc.name },
									freeze: true,
									callback: function() {
										frappe.show_alert({ message: __("Submitted at available hours."), indicator: "green" });
										frappe.hide_msgprint();
										frm.reload_doc();
									},
								});
							},
						},
						secondary_action: {
							label: __("Notify Account Manager"),
							action: () => {
								frappe.call({
									method: "phamos.phamos.doctype.timesheet_record.timesheet_record.notify_pm_of_time_limit",
									args: { name: frm.doc.name },
									freeze: true,
									callback: function() {
										frappe.show_alert({
											message: __("The account manager has been emailed and can submit this record."),
											indicator: "green",
										});
										frappe.hide_msgprint();
									},
								});
							},
						},
					});
					resolve();
				},
			});
		});
	},
	refresh: function(frm) {
		if(!frm.is_new() && frm.doc.docstatus==0) {
			frm.add_custom_button(__('Mark Complete'), function() {
				frm.trigger("mark_complete");
			});
		}
	},
	project: function(frm) {
		//Filter task based on project if project is selected first
		frm.set_query("task", () => {
			let filters = {};
			if (frm.doc.project) filters["project"] = frm.doc.project;
			return {
				filters: filters
			}
		});
	},
	task: function(frm) {
		//set project if task is clicked first
		if(!frm.doc.project){
			frappe.db.get_value('Task', frm.doc.task, 'project', (r) => {
				frm.set_value("project",r.project);
				});
			}
	},
	mark_complete: function(frm) {
		frappe.prompt([
			{
				label: 'Time', fieldname: 'to_time', fieldtype: 'Datetime',
				default: frappe.datetime.now_datetime(), reqd: 1
			},
			{
				fieldtype: 'Column Break'
			},
			{
				label: 'What I did ', fieldname: 'result',
				fieldtype: 'Small Text', reqd: 1
			},
		], (values) => {
			if (values.to_time > frm.doc.from_time) {
				frm.set_value("result", values.result);
				frm.set_value("to_time", values.to_time);
				frappe.call({
							method:"phamos.phamos.doctype.timesheet_record.timesheet_record.set_actual_time",
							args: {
								"from_time": frm.doc.from_time,
								"to_time": values.to_time
							},
							callback: function(r) {
								if(!r.exc){
									frm.set_value("actual_time", r.message);
									frm.save();
								}
							}
						});
			}
			else {
				frappe.throw(__("To Time cannot be less than From Time"))
			}
		})
	}
});