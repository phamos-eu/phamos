frappe.ui.form.on("Delivery Note", {
	setup(frm) {
		frm.can_make_methods = { ...frm.can_make_methods, Timesheet: () => false };
	},
});
