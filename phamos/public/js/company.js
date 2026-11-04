// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

// Events tab (phamos/setup/event_schedule.py): same email account filter as on Team.
frappe.ui.form.on("Company", {
	setup(frm) {
		setup_daily_schedule_email_account_query(frm);
	},
	refresh(frm) {
		setup_daily_schedule_email_account_query(frm);
	},
});
