// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on('Escalation', {
	refresh(frm) {
		frm.trigger('update_days');
		frm.trigger('fetch_snapshot_fields');
	},

	open_date(frm) {
		frm.trigger('update_days');
		frm.trigger('fetch_snapshot_fields');
	},

	close_date(frm) {
		frm.trigger('update_days');
	},

	status(frm) {
		if (frm.doc.status === 'Resolved' && !frm.doc.close_date) {
			frm.set_value('close_date', frappe.datetime.get_today());
		}
		frm.trigger('update_days');
	},

	implementation(frm) {
		frm.trigger('fetch_snapshot_fields');
	},

	update_days(frm) {
		if (!frm.doc.open_date) return;
		const end_date = (frm.doc.status === 'Resolved' && frm.doc.close_date)
			? frm.doc.close_date
			: frappe.datetime.get_today();
		const days = frappe.datetime.get_diff(end_date, frm.doc.open_date);
		frm.set_value('days_of_escalation', days >= 0 ? days : 0);
	},

	fetch_snapshot_fields(frm) {
		if (!frm.doc.implementation || !frm.doc.open_date) return;
		frappe.call({
			method: 'phamos.phamos.doctype.escalation.escalation.get_status_before_date',
			args: {
				implementation: frm.doc.implementation,
				open_date: frm.doc.open_date
			},
			callback(r) {
				if (r.message && Object.keys(r.message).length) {
					frm.set_value('maturity_level', r.message.maturity_level);
					frm.set_value('implementation_status', r.message.forecast);
				}
			}
		});
	}
});
