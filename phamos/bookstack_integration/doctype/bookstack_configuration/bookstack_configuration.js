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

			frm.add_custom_button(__("Sync…"), () => bookstack_sync_dialog(frm), __("Actions"));

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

// Parts of a sync, in the order the server runs them (phamos.bookstack_integration.sync.SYNC_STEPS, #2029).
// Functions, not top-level consts: Desk may evaluate a form script more than once.
function bookstack_sync_steps() {
	return [
	{ step: "roles", label: __("Roles") },
	{ step: "users", label: __("Users"), description: __("Links each user to the roles synced before.") },
	{ step: "books", label: __("Books") },
	{ step: "shelves", label: __("Shelves"), description: __("One call per shelf; links the books.") },
	{ step: "chapters", label: __("Chapters") },
	{ step: "pages", label: __("Pages") },
	{
		step: "content",
		label: __("Website content"),
		description: __("Copies the pages of books published on the website."),
	},
	];
}

function bookstack_step_labels() {
	return {
		...Object.fromEntries(bookstack_sync_steps().map((s) => [s.step, s.label])),
		removed: __("Removed (deleted in BookStack)"),
	};
}

function bookstack_sync_dialog(frm) {
	const steps_config = bookstack_sync_steps();
	const d = new frappe.ui.Dialog({
		title: __("Sync from {0}", [frm.doc.title]),
		fields: [
			{ fieldtype: "Heading", label: __("What to sync") },
			...steps_config.map((s) => ({
				fieldname: s.step,
				fieldtype: "Check",
				label: s.label,
				description: s.description,
				default: 1,
			})),
			{ fieldtype: "Section Break" },
			{
				fieldname: "remove_deleted_records",
				fieldtype: "Check",
				label: __("Remove records deleted in BookStack"),
				description: __("Only for the ticked shelves, books, chapters and pages."),
				default: 1,
			},
		],
		primary_action_label: __("Sync"),
		primary_action(values) {
			const steps = steps_config.filter((s) => values[s.step]).map((s) => s.step);
			if (!steps.length) {
				frappe.msgprint(__("Choose at least one part to sync."));
				return;
			}
			d.hide();
			frm.call({
				doc: frm.doc,
				method: "sync_all",
				args: { steps, remove_deleted_records: values.remove_deleted_records ? 1 : 0 },
				freeze: true,
				freeze_message: __("Syncing Bookstack..."),
			}).then((r) => {
				if (r.message) bookstack_show_sync_result(r.message);
				frm.reload_doc();
			});
		},
	});
	d.show();
}

function bookstack_show_sync_result(stats) {
	const labels = bookstack_step_labels();
	const rows = Object.keys(labels)
		.filter((step) => step in stats)
		.map((step) => {
			const value = stats[step];
			const failed = typeof value === "string" && value.startsWith("error");
			return `<tr><td>${frappe.utils.escape_html(labels[step])}</td>
				<td class="${failed ? "text-danger" : "text-right"}">${frappe.utils.escape_html(String(value))}</td></tr>`;
		})
		.join("");
	frappe.msgprint({
		title: stats.errors ? __("Sync finished with errors") : __("Sync complete"),
		indicator: stats.errors ? "orange" : "green",
		message: `<table class="table table-sm"><tbody>${rows}</tbody></table>`,
	});
}
