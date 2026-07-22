["Department", "Employee"].forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		setup(frm) {
			if (window.phamos && phamos.functional_calendar) {
				phamos.functional_calendar.setup_email_account_query(frm);
			}
		},
		refresh(frm) {
			if (window.phamos && phamos.functional_calendar) {
				phamos.functional_calendar.setup_email_account_query(frm);
			}
		},
	});
});
