// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("GitLab Settings", {
    refresh(frm) {
        frm.add_custom_button('Sync Projects', function () {
            frappe.call({
                method: 'phamos.gitlab_integration.gitlab_utils.sync_projects_only',
                callback: function (r) {
                    frappe.msgprint(r.message || "Projects synced!");
                }
            });
        });

        frm.add_custom_button('Sync Issues', function () {
            frappe.call({
                method: 'phamos.gitlab_integration.gitlab_utils.sync_issues_only',
                callback: function (r) {
                    frappe.msgprint(r.message || "Issues synced!");
                }
            });
        });
        frm.add_custom_button('Sync Milestones', function () {
            frappe.call({
                method: 'phamos.gitlab_integration.gitlab_utils.sync_gitlab_milestones',
                callback: function (r) {
                    frappe.msgprint(r.message || "Milestones synced!");
                }
            });
        });
	},
});
