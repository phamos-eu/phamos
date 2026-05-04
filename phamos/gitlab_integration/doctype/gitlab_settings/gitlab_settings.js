// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("GitLab Settings", {
    refresh(frm) {

        let sync_group = __("GitLab Sync");

        frm.add_custom_button('Sync Groups', function () {
            frappe.call({
                method: 'phamos.gitlab_integration.gitlab_utils.sync_groups_only',
                callback: function (r) {
                    frappe.msgprint(r.message || "Groups synced!");
                }
            });
        }, sync_group);

        frm.add_custom_button('Sync Projects', function () {
            frappe.call({
                method: 'phamos.gitlab_integration.gitlab_utils.sync_projects_only',
                callback: function (r) {
                    frappe.msgprint(r.message || "Projects synced!");
                }
            });
        }, sync_group);

        frm.add_custom_button('Sync All Issues', function () {
            frappe.call({
                method: 'phamos.gitlab_integration.gitlab_utils.sync_all_issues',
                callback: function (r) {
                    frappe.msgprint(r.message || "All issues synced!");
                }
            });
        }, sync_group);

        frm.add_custom_button('Sync Milestones', function () {
            frappe.call({
                method: 'phamos.gitlab_integration.gitlab_utils.sync_gitlab_milestones',
                callback: function (r) {
                    frappe.msgprint(r.message || "Milestones synced!");
                }
            });
        }, sync_group);

        frm.add_custom_button('Sync Labels', function () {
            frappe.call({
                method: 'phamos.gitlab_integration.gitlab_utils.sync_gitlab_labels',
                callback: function (r) {
                    frappe.msgprint(r.message || "Labels synced!");
                }
            });
        }, sync_group);

        frm.add_custom_button('Set Webhooks', function () {
            frappe.call({
                method: 'phamos.gitlab_integration.gitlab_utils.register_webhooks_for_all_projects',
                callback: function (r) {
                    frappe.msgprint(r.message || "Webhooks registered!");
                }
            });
        }, sync_group);

    },
});