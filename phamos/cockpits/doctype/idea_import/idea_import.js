// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

// Import ideas from a NextChapter site (#1776): load the accounts, map them, import.
frappe.ui.form.on("Idea Import", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Load accounts"), () => call(frm, "load_accounts", __("Reading NextChapter…")));
		frm.add_custom_button(__("Import"), () => {
			frappe.confirm(
				__("Import all ideas and writing sessions now? Ideas already imported are skipped."),
				() => call(frm, "run_import", __("Importing ideas…"))
			);
		}).addClass("btn-primary");
	},
});

function call(frm, method, message) {
	const run = () =>
		frappe.call({
			method: `phamos.cockpits.doctype.idea_import.idea_import.${method}`,
			args: { name: frm.doc.name },
			freeze: true,
			freeze_message: message,
			callback: (r) => {
				frm.reload_doc();
				if (method === "run_import" && r.message) {
					frappe.show_alert({
						message: __("{0} ideas and {1} sessions imported, {2} already there", [
							r.message.ideas_created,
							r.message.sessions_created,
							r.message.skipped,
						]),
						indicator: "green",
					});
				}
			},
		});
	frm.is_dirty() ? frm.save().then(run) : run();
}
