// Copyright (c) 2023, Phamos GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on('Timesheet Record', {
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