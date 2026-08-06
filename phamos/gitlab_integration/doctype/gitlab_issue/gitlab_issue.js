// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

function clearFalseUnsavedState(frm) {
	if (frm.is_new()) {
		return;
	}

	const clearNow = () => {
		if (frm.is_new() || !frm.doc.__unsaved) {
			return;
		}

		frm.doc.__unsaved = 0;
		if (frm.page && frm.page.clear_indicator) {
			frm.page.clear_indicator();
		}
		frm.refresh_header();
	};

	[0, 300].forEach((delay) => setTimeout(clearNow, delay));

	// Catch late async UI updates (markdown/table rendering, background calls).
	if (typeof frappe.after_ajax === "function") {
		frappe.after_ajax(clearNow);
	}
}

frappe.ui.form.on("GitLab Issue", {
	onload_post_render(frm) {
		// Some records can appear as dirty right after render due to widget
		// normalization. Reset only once after load; real user edits still mark
		// the form as dirty normally.
		if (frm.__initial_dirty_fix_applied) {
			return;
		}
		frm.__initial_dirty_fix_applied = true;
		clearFalseUnsavedState(frm);
	},
	refresh(frm) {
		clearFalseUnsavedState(frm);
	},
	after_save(frm) {
		// Markdown/table widgets may flip __unsaved back to true right after save.
		clearFalseUnsavedState(frm);
	},
});
