frappe.provide('erpnext.phamos');
erpnext.phamos.MakeTimeSheetDialog = class MakeTimeSheetDialog {
	constructor(opts) {
		$.extend(this, opts);
		this.setup(opts.doc);
	}

	setup(doc) {
		this.make_dialog(doc);
		// this.on_close_dialog();
	}

	make_dialog(doc) {
		var me = this;

		this.data = this.oldest ? this.oldest : [];
		let title = __("Making Timesheet");
		let size = "large";
		let fields = [
			{
				fieldname: "project", fieldtype: "Link",
				label: "Project", options: "Project",
				default: doc.name, reqd: 1,
			},
			{
				fieldname: "customer", fieldtype: "Link",
				options: "Customer", label: "Customer",
				default: doc.customer, //reqd: 1,
			},
			{
				fieldname: "activity_type", fieldtype: "Link",
				label: "Activity Type", options: "Activity Type",
				reqd: 1,
			},
			{
				fieldname: "task", fieldtype: "Link",
				label: "Task", options: "Task",
				// reqd: 1,
			},
			{
				fieldtype: "Column Break"
			},
			{
				fieldname: "from_time", fieldtype: "Datetime",
				label: "From Time",
				// default: frappe.datetime.convert_to_system_tz(frappe.datetime.add_months(frappe.datetime.now_datetime(), -1)),
				default: frappe.datetime.now_datetime(),
				reqd: 1,
			},
			{
				fieldname: "expected_time", fieldtype: "Duration",
				label: "Expected Time", reqd: 1,
			},
			{
				fieldname: "goal", fieldtype: "Small Text",
				label: "Goal", reqd: 1,
			},

		]

		this.dialog = new frappe.ui.Dialog({
			title: title,
			size: size,
			fields: fields
		});

		this.dialog.set_primary_action(__('Make'), function () {
			frappe.run_serially([
				() => me.make_timesheet(),
				() => me.dialog.hide()
			])

		});

		this.dialog.show();
	}

	on_close_dialog() {
		this.dialog.get_close_btn().on('click', () => {
			this.on_close && this.on_close(this.item);
		});
	}

	make_timesheet() {
		let message;
		var me = this;
		me.values = me.dialog.get_values();
		frappe.call({
			method: "phamos.events.project.make_timesheet",
			args: {
				doc: me.values
			},
			callback: function (r) {
				if (r.exc) { frappe.msgprint(r.exc); return; }
				if (r.message && !r.exc) {
					frappe.set_route("Form", "Timesheet Record", r.message);
				}
			}
		});
	}

};