// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("GitLab Settings", {
	refresh(frm) {
        	frm.add_custom_button('Sync Projects & Issues', function () {
		// Check if job is queued or started
		frappe.call({
			method: 'phamos.gitlab_integration.gitlab_utils.is_job_running',
			callback: function (r) {
				if (r.message && r.message.is_running) {
					// Job is queued or started
					frappe.msgprint({
						title: 'Sync in Progress',
						message: r.message.message,
						indicator: 'orange'
					});
				} else {
					// No active job, proceed with sync
					frappe.call({
						method: 'phamos.gitlab_integration.gitlab_utils.sync_gitlab_data',
						callback: function () {
							frappe.msgprint("GitLab data synced!");
						}
					});
				}
			}
		});
	});
	},
});