// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Implementation Chapter", {
	refresh(frm) {
		frm.trigger("toggle_agreed_content_readonly");

		if (!frm.is_new() && frm.doc.status === "Draft") {
			frm.add_custom_button(__("Set as Planned"), () => {
				frappe.confirm(
					__(
						"This locks the agreed content (title, description, dates) as an immutable Revision 1 and moves this Chapter to Planned. This cannot be undone. Continue?"
					),
					() => {
						frappe.call({
							method:
								"phamos.phamos.doctype.implementation_chapter.implementation_chapter.set_as_planned",
							args: { name: frm.doc.name },
							freeze: true,
							freeze_message: __("Setting as Planned..."),
							callback: () => {
								frm.reload_doc();
							},
						});
					}
				);
			}).addClass("btn-primary");
		}
	},
	toggle_agreed_content_readonly(frm) {
		const locked = frm.doc.status && frm.doc.status !== "Draft";
		["chapter_title", "chapter_introduction", "full_chapter_description", "planned_start", "target_date"].forEach(
			(fieldname) => {
				frm.set_df_property(fieldname, "read_only", locked ? 1 : 0);
			}
		);
		frm.refresh_fields();
	},
});
