// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("GitLab Project", {
    refresh(frm) {
        frm.add_custom_button(__("Sync Issues"), function () {
            frappe.call({
                method: "phamos.gitlab_integration.gitlab_utils.sync_issues_for_project",
                args: {
                    project_name: frm.doc.name
                },
                freeze: true,
                freeze_message: __("Syncing Issues..."),
                callback: function(r) {
                    frappe.msgprint(r.message || __("Issues synced successfully"));
                    frm.reload_doc();
                }
            });
        });
    }
});