// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("GitLab Project", {
    refresh(frm) {
        frm.add_custom_button(__("Sync Issues"), () => {
            frappe.call({
                method: "phamos.gitlab_integration.gitlab_utils.sync_issues_for_project",
                args: {
                    project_name: frm.doc.name,
                },
                callback: (r) => {
                    frappe.msgprint(r.message || __("Issues synced!"));
                },
            });
        });
    },
});