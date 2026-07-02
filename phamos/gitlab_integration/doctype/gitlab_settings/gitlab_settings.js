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

        let report_group = __("Weekly Customer Report");

        frm.add_custom_button('Backfill Issue Comments', function () {
            frappe.confirm(
                __("Fetch and store historical (non-system) comments for all synced GitLab Issues? This can take a while for large projects."),
                () => {
                    frappe.call({
                        method: 'phamos.gitlab_integration.gitlab_utils.backfill_issue_comments',
                        freeze: true,
                        freeze_message: __("Backfilling GitLab issue comments..."),
                        callback: function (r) {
                            frappe.msgprint(r.message || "Comments backfilled!");
                        }
                    });
                }
            );
        }, report_group);

        frm.add_custom_button('Send Weekly Reports Now (Test)', function () {
            frappe.confirm(
                __("Send the weekly customer report now, to every Implementation with at least one stakeholder opted in to 'Weekly Report'? This sends real emails."),
                () => {
                    frappe.call({
                        method: 'phamos.gitlab_integration.generate_weekly_report.send_weekly_reports_for_all_implementations',
                        freeze: true,
                        freeze_message: __("Generating and sending weekly reports..."),
                        callback: function (r) {
                            const m = r.message || {};
                            frappe.msgprint({
                                title: __("Weekly reports finished"),
                                message: __("Sent: {0}<br>Failed: {1}", [
                                    (m.sent || []).join(", ") || "—",
                                    (m.failed || []).join(", ") || "—",
                                ]),
                                indicator: (m.failed || []).length ? "orange" : "green",
                            });
                        }
                    });
                }
            );
        }, report_group);

    },
});