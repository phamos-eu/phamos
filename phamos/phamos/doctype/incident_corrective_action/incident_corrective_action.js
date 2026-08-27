// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Incident Corrective Action", {
	refresh(frm) {
		if (frm.is_new() || !frm.fields_dict.team) {
			return;
		}
		_add_share_button(frm);
	},
});

function _add_share_button(frm) {
	const $bulk_actions = frm.fields_dict.team.grid.wrapper.find(".grid-bulk-actions");
	if ($bulk_actions.find(".btn-share-team").length) {
		return;
	}
	$(`<button type="button" class="btn btn-sm btn-share-team">${__("Share")}</button>`)
		.css({
			background: "#fff",
			color: "#1a1a1a",
			border: "1px solid var(--gray-400)",
			"font-weight": "600",
			"box-shadow": "0 1px 2px rgba(0, 0, 0, 0.2)",
		})
		.appendTo($bulk_actions)
		.on("click", () => _share_with_team(frm));
}

function _share_with_team(frm) {
	const call_and_open = () => {
		frappe.call({
			method: "phamos.phamos.doctype.incident_corrective_action.incident_corrective_action.share_with_internal_team",
			args: { name: frm.doc.name },
			callback: () => _refresh_share_sidebar_then_open(frm),
		});
	};

	if (frm.is_dirty()) {
		frm.save().then(call_and_open);
		return;
	}

	call_and_open();
}

function _refresh_share_sidebar_then_open(frm) {
	frappe.call({
		method: "frappe.share.get_users",
		args: { doctype: frm.doctype, name: frm.doc.name },
		callback: (r) => {
			const shared = r.message || [];
			frm.get_docinfo().shared = shared;
			if (frm.shared) {
				frm.shared.shared = shared;
				frm.shared.refresh();
			}
			frm.share_doc();
		},
	});
}

frappe.ui.form.on("Corrective Action Item", {
	to_be_implemented(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.parentfield !== "corrective_actions" || !row.to_be_implemented) {
			return;
		}
		frm.add_child("corrective_action_implementation", {
			action: row.action,
			owner: row.owner,
		});
		frm.refresh_field("corrective_action_implementation");
		frappe.show_alert({ message: __("Copied to D6"), indicator: "green" });
	},
});
