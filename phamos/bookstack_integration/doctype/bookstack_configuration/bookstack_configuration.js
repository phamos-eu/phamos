// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bookstack Configuration", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Test Connection"), () => {
				frm.call("test_connection").then((r) => {
					if (r.message) frappe.show_alert({ message: r.message, indicator: "green" });
				});
			});

			frm.add_custom_button(__("Sync All"), () => {
				frappe.confirm(
					__("Pull shelves, books, chapters, pages, users and roles from {0}?", [frm.doc.title]),
					() => {
						frappe.show_alert({ message: __("Sync started..."), indicator: "blue" });
						frm.call({
							doc: frm.doc,
							method: "sync_all",
							freeze: true,
							freeze_message: __("Syncing Bookstack..."),
						}).then((r) => {
							if (r.message) frappe.msgprint({ title: __("Sync complete"), message: `<pre>${JSON.stringify(r.message, null, 2)}</pre>`, indicator: "green" });
							frm.reload_doc();
						});
					}
				);
			}, __("Actions"));

			frm.add_custom_button(__("Open Bookstack"), () => {
				if (frm.doc.instance_url) window.open(frm.doc.instance_url, "_blank");
			});

			frm.add_custom_button(__("Provision Users..."), () => {
				const d = new frappe.ui.Dialog({
					title: __("Provision Bookstack Users"),
					fields: [
						{
							fieldname: "users_csv",
							fieldtype: "Long Text",
							label: __("Users (one per line: name,email,role[,language])"),
							reqd: 1,
							description: __("Example: Alice Example,alice@example.com,Admin,en")
						},
						{ fieldname: "send_invite", fieldtype: "Check", label: __("Send Invite Email"), default: frm.doc.send_invite_by_default }
					],
					primary_action_label: __("Create"),
					primary_action(values) {
						frappe.call({
							method: "phamos.bookstack_integration.provisioning.bulk_create_users",
							args: {
								instance: frm.doc.name,
								users_csv: values.users_csv,
								send_invite: values.send_invite ? 1 : 0
							},
							freeze: true,
							freeze_message: __("Creating users...")
						}).then((r) => {
							d.hide();
							frappe.msgprint({ title: __("Provisioning result"), message: `<pre>${JSON.stringify(r.message, null, 2)}</pre>`, indicator: "green" });
						});
					}
				});
				d.show();
			}, __("Actions"));
		}
	}
});
