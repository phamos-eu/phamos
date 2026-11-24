// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stakeholder Meeting", {
	refresh(frm) {
		frm.set_query("chapter", "chapter_reviews", () => ({
			filters: { implementation: frm.doc.implementation, status: ["!=", "Cancelled"] },
		}));
	},

	implementation(frm) {
		// Show attendees and chapter reviews right away instead of after the first save.
		if (frm.is_new()) {
			frm.call("fetch_from_implementation");
		}
	},
});

frappe.ui.form.on("Stakeholder Meeting Chapter Review", {
	progress(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.progress === "Complete" && !row.chapter_status_after) {
			frappe.model.set_value(cdt, cdn, "chapter_status_after", "Completed");
		}
	},

	chapter(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.chapter || !frm.doc.implementation) {
			return;
		}

		frappe
			.call({
				method: "phamos.phamos.doctype.stakeholder_meeting.stakeholder_meeting.get_chapter_review_row",
				args: { implementation: frm.doc.implementation, chapter: row.chapter },
			})
			.then((r) => {
				if (r.message && locals[cdt][cdn]) {
					const values = { ...r.message };
					delete values.chapter;
					frappe.model.set_value(cdt, cdn, values);
				}
			});
	},

	scope_change(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.scope_change || !row.chapter) {
			return;
		}

		// Pre-fill from the Chapter, only into fields that are still empty, so
		// re-checking Scope Change never overwrites manual edits.
		const fields = {
			proposed_chapter_title: "chapter_title",
			proposed_chapter_introduction: "chapter_introduction",
			proposed_full_chapter_description: "full_chapter_description",
			proposed_planned_start: "planned_start",
			proposed_target_date: "target_date",
		};
		frappe.db.get_value("Implementation Chapter", row.chapter, Object.values(fields)).then((r) => {
			const chapter = r.message || {};
			const current = locals[cdt][cdn];
			if (!current) {
				return;
			}
			const values = {};
			for (const [proposed, source] of Object.entries(fields)) {
				if (!current[proposed] && chapter[source]) {
					values[proposed] = chapter[source];
				}
			}
			frappe.model.set_value(cdt, cdn, values);
		});
	},
});
