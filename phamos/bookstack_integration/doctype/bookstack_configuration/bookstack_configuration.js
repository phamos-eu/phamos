// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bookstack Configuration", {
	onload(frm) {
		// Result of a sync started with "Sync All" (phamos.bookstack_integration.sync.run_sync_job).
		// Registered once per page load; the Bookstack Browser has a listener of its own.
		if (frappe._bookstack_sync_listener) return;
		frappe._bookstack_sync_listener = true;
		frappe.realtime.on("bookstack_sync_done", (stats) => {
			if (cur_frm?.doctype !== "Bookstack Configuration") return;
			const failed = stats.failed || stats.errors;
			frappe.msgprint({
				title: failed ? __("Sync finished with errors") : __("Sync complete"),
				message: `<pre>${frappe.utils.escape_html(JSON.stringify(stats, null, 2))}</pre>`,
				indicator: failed ? "orange" : "green",
			});
			if (cur_frm.doc.name === stats.instance) cur_frm.reload_doc();
		});
	},
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
						// A background job (#2004): a first copy of a big book takes minutes.
						frappe
							.xcall("phamos.bookstack_integration.sync.start_sync", { instance: frm.doc.name })
							.then(() =>
								frappe.show_alert({
									message: __("Sync started in the background. The result shows here when it is done."),
									indicator: "blue",
								}, 10)
							);
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
