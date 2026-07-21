// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bookstack User", {
	refresh(frm) {
		if (frm.doc.instance) {
			frappe.db.get_value("Bookstack Configuration", frm.doc.instance, "instance_url").then((r) => {
				const base = r.message && r.message.instance_url;
				if (base && frm.doc.bookstack_id) {
					frm.add_custom_button(__("Open in Bookstack"), () =>
						window.open(`${base}/settings/users/${frm.doc.bookstack_id}`, "_blank")
					);
				}
			});
		}
	}
});
