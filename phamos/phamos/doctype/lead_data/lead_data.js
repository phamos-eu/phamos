// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lead Data", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Refresh Matches"), () => {
			frappe.call({
				method: "phamos.phamos.doctype.lead_data.lead_data.refresh_handoff_status",
				args: { lead_data_name: frm.doc.name },
				freeze: true,
				callback(r) {
					if (r.message) {
						frm.reload_doc();
						show_review_dialog(frm, r.message);
					}
				},
			});
		});

		const status = frm.doc.handoff_status || "Draft";
		if (!["Created", "Skipped"].includes(status)) {
			frm
				.add_custom_button(__("Create CRM Records"), () => {
					open_handoff_dialog(frm);
				})
				.addClass("btn-primary");
		}

		if (status === "Possible Duplicate" || status === "Ready") {
			frm.add_custom_button(__("Skip"), () => {
				frappe.call({
					method: "phamos.phamos.doctype.lead_data.lead_data.skip_handoff",
					args: { lead_data_name: frm.doc.name },
					callback() {
						frm.reload_doc();
					},
				});
			});
		}

		if (frm.doc.erpnext_lead) {
			frm.add_custom_button(__("Open Lead"), () => {
				frappe.set_route("Form", "Lead", frm.doc.erpnext_lead);
			});
		}
	},
});

function open_handoff_dialog(frm) {
	frappe.call({
		method: "phamos.phamos.doctype.lead_data.lead_data.get_review_payload",
		args: { lead_data_name: frm.doc.name },
		freeze: true,
		callback(r) {
			if (!r.message) return;
			show_review_dialog(frm, r.message, true);
		},
	});
}

function show_review_dialog(frm, review, allow_create) {
	const readiness = review.readiness || {};
	const matches = review.matches || [];
	const party = review.party_hint || {};

	let html = `<p><b>${__("Score")}:</b> ${readiness.score ?? "—"} · <b>${__("Status")}:</b> ${
		review.handoff_status || ""
	}</p>`;

	if (party.message) {
		html += `<div class="alert alert-info">${frappe.utils.escape_html(party.message)}</div>`;
	}

	if ((readiness.blockers || []).length) {
		html += `<p><b>${__("Blockers")}</b></p><ul>`;
		readiness.blockers.forEach((b) => {
			html += `<li>${frappe.utils.escape_html(b)}</li>`;
		});
		html += `</ul>`;
	}
	if ((readiness.warnings || []).length) {
		html += `<p><b>${__("Warnings")}</b></p><ul>`;
		readiness.warnings.forEach((w) => {
			html += `<li>${frappe.utils.escape_html(w)}</li>`;
		});
		html += `</ul>`;
	}

	if (matches.length) {
		html += `<p><b>${__("Possible matches")}</b></p><ul>`;
		matches.slice(0, 12).forEach((m) => {
			html += `<li><b>${frappe.utils.escape_html(m.doctype)}</b> ${frappe.utils.escape_html(
				m.title || m.name
			)} <code>${frappe.utils.escape_html(m.name)}</code> (${m.score}) — ${frappe.utils.escape_html(
				m.reason || ""
			)}</li>`;
		});
		html += `</ul>`;
	} else {
		html += `<p>${__("No strong CRM matches found.")}</p>`;
	}

	const fields = [
		{ fieldtype: "HTML", options: html },
		{
			fieldname: "customer",
			fieldtype: "Link",
			options: "Customer",
			label: __("Customer (Converted Lead)"),
			default: party.customer || "",
		},
		{
			fieldname: "supplier",
			fieldtype: "Link",
			options: "Supplier",
			label: __("Supplier"),
			default: party.supplier || "",
		},
		{
			fieldname: "force",
			fieldtype: "Check",
			label: __("Create anyway despite duplicates"),
			default: 0,
		},
	];

	const d = new frappe.ui.Dialog({
		title: __("CRM Handoff"),
		fields,
		primary_action_label: allow_create ? __("Create Lead + Contact") : __("Close"),
		primary_action(values) {
			if (!allow_create) {
				d.hide();
				return;
			}
			frappe.call({
				method: "phamos.phamos.doctype.lead_data.lead_data.create_crm_records",
				args: {
					lead_data_name: frm.doc.name,
					force: values.force ? 1 : 0,
					customer: values.customer || "",
					supplier: values.supplier || "",
				},
				freeze: true,
				freeze_message: __("Creating CRM records..."),
				callback(res) {
					d.hide();
					if (res.message && res.message.ok) {
						frappe.show_alert({
							message: res.message.message || __("Created"),
							indicator: "green",
						});
						if (res.message.lead) {
							frappe.set_route("Form", "Lead", res.message.lead);
						}
						frm.reload_doc();
					}
				},
			});
		},
	});

	if (allow_create && (party.contact || party.lead)) {
		d.set_secondary_action_label(__("Link Existing"));
		d.set_secondary_action(() => {
			frappe.call({
				method: "phamos.phamos.doctype.lead_data.lead_data.link_crm_records",
				args: {
					lead_data_name: frm.doc.name,
					lead: party.lead || "",
					contact: party.contact || "",
					customer: d.get_value("customer") || party.customer || "",
					supplier: d.get_value("supplier") || party.supplier || "",
				},
				freeze: true,
				callback() {
					d.hide();
					frm.reload_doc();
				},
			});
		});
	}

	d.show();
}
