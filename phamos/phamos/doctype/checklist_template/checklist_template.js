// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Checklist Template", {
	setup(frm) {
		// Hide Connections "+" for Checklist — create only via "Create Checklist"
		// so items are snapshotted from the template instead of an empty Quick Entry.
		frm.can_make_methods = {
			Checklist: () => false,
		};

		frm.set_query("checklist_template_owner", () => ({
			query:
				"phamos.phamos.doctype.checklist_template.checklist_template.checklist_template_owner_query",
		}));
	},

	refresh(frm) {
		if (frm.doc.docstatus !== 1) {
			return;
		}

		frm.add_custom_button(__("Create Checklist"), () => {
			show_create_checklist_dialog(frm);
		});
	},
});

function show_create_checklist_dialog(frm) {
	const fields = [
		{
			fieldname: "checklist_name",
			fieldtype: "Data",
			label: __("Checklist Name"),
			reqd: 1,
			default: frm.doc.name,
		},
		{
			fieldname: "reference_record",
			fieldtype: "Link",
			label: __("Reference Record"),
			options: frm.doc.document,
			description: __("Optional. Leave empty to create without linking a specific record."),
		},
	];

	const dialog = new frappe.ui.Dialog({
		title: __("Create Checklist"),
		fields,
		primary_action_label: __("Create"),
		primary_action(values) {
			frappe.call({
				method:
					"phamos.phamos.doctype.checklist_template.checklist_template.create_checklist_from_template",
				args: {
					template_name: frm.doc.name,
					checklist_name: values.checklist_name,
					reference_record: values.reference_record || null,
				},
				freeze: true,
				freeze_message: __("Creating Checklist..."),
				callback(r) {
					if (!r.message) {
						return;
					}
					dialog.hide();
					frappe.set_route("Form", "Checklist", r.message);
				},
			});
		},
	});

	dialog.show();
}
