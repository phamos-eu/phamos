// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stakeholder Meeting", {
	refresh(frm) {
		frm.set_query("chapter", "chapter_reviews", () => ({
			filters: { implementation: frm.doc.implementation, status: ["!=", "Cancelled"] },
		}));
		frm.set_query("chapter", "decisions", () => ({
			filters: { implementation: frm.doc.implementation, status: ["!=", "Cancelled"] },
		}));
	},
});

frappe.ui.form.on("Stakeholder Meeting Chapter Review", {
	scope_change(frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		// Only pre-fill once, the first time this row's Scope Change is checked,
		// so re-checking it after unchecking never clobbers manual edits.
		if (!row.scope_change || row.proposed_chapter_title || !row.current_revision) {
			return;
		}

		frappe.db.get_doc("Implementation Chapter Revision", row.current_revision).then((revision) => {
			frappe.model.set_value(cdt, cdn, "proposed_chapter_title", revision.chapter_title);
			frappe.model.set_value(cdt, cdn, "proposed_chapter_introduction", revision.chapter_introduction);
			frappe.model.set_value(cdt, cdn, "proposed_full_chapter_description", revision.full_chapter_description);
			frappe.model.set_value(cdt, cdn, "proposed_planned_start", revision.planned_start);
			frappe.model.set_value(cdt, cdn, "proposed_target_date", revision.target_date);
		});
	},
});
