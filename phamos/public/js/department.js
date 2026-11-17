// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

// Event Schedule (phamos/setup/event_schedule.py, #1949): same email account filter as on Team.
frappe.ui.form.on("Department", {
	setup(frm) {
		setup_daily_schedule_email_account_query(frm);
	},
	refresh(frm) {
		setup_daily_schedule_email_account_query(frm);
	},
});
