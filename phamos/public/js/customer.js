// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Customer", {
    refresh(frm) {

        frm.add_custom_button('Create Gitlab Group', function () {
            frappe.call({
                method: 'phamos.gitlab_integration.gitlab_group_utils.create_gitlab_group_for_customer',
                args: {
                    customer_name: frm.doc.name
                },
                callback: function (r) {
                    frappe.msgprint(r.message || "Gitlab Group created successfully!");
                }
            });
        }, __("Create"));

    },
});