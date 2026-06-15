function register_checklist_popup_handlers(doctypes) {
	if (!Array.isArray(doctypes) || !doctypes.length) {
		return;
	}

	doctypes.forEach((doctype) => {
		frappe.ui.form.on(doctype, {
			onload(frm) {
				frm.__checklist_dialog_shown = false;
			},
			refresh(frm) {
				if (frm.is_new() || frm.__checklist_dialog_shown) {
					return;
				}

				frm.__checklist_dialog_shown = true;
				requestAnimationFrame(() => {
					setTimeout(() => show_linked_checklists_dialog(frm), 100);
				});
			},
		});
	});

	if (window.cur_frm && doctypes.includes(cur_frm.doctype)) {
		cur_frm.trigger("refresh");
	}
}

frappe.call({
	method: "phamos.api.get_popup_doctypes",
	callback(r) {
		register_checklist_popup_handlers(r.message || []);
	},
	error(r) {
		console.error("Failed to load popup doctypes", r);
	},
});

function show_linked_checklists_dialog(frm) {
	frappe.call({
		method: "phamos.phamos.doctype.marketing_content.marketing_content.get_linked_checklists",
		args: {
			doctype: frm.doctype,
			name: frm.doc.name,
		},
		callback(r) {
			const checklists = r.message || [];

			if (!checklists.length) {
				return;
			}

			const dialog = new frappe.ui.Dialog({
				title: __("Linked Checklist Overview"),
				size: "large",
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "linked_checklists_html",
					},
				],
				primary_action_label: __("Close"),
				primary_action() {
					dialog.hide();
				},
			});

			dialog.fields_dict.linked_checklists_html.$wrapper.html(
				build_checklist_dialog_html(checklists)
			);

			dialog.show();
		},
	});
}

function build_checklist_dialog_html(checklists) {
	const rows = checklists
		.map((row) => {
			const percentage = row.completion_percentage || 0;

			const badge_color = {
				Completed: "green",
				"In Progress": "orange",
				"Not Started": "gray",
			}[row.status] || "blue";

			return `
				<tr>
					<td>
						<a href="/app/checklist/${encodeURIComponent(row.name)}"
						   target="_blank">
							${frappe.utils.escape_html(row.name)}
						</a>
					</td>

					<td>
						<span class="indicator ${badge_color}">
							${frappe.utils.escape_html(row.status || "-")}
						</span>
					</td>

					<td style="min-width:220px;">
						<div class="progress">
							<div
								class="progress-bar bg-success"
								role="progressbar"
								style="width:${percentage}%"
								aria-valuenow="${percentage}"
								aria-valuemin="0"
								aria-valuemax="100"
							>
								${percentage}%
							</div>
						</div>
					</td>
				</tr>
			`;
		})
		.join("");

	return `
		<div style="max-height:400px; overflow:auto;">
			<table class="table table-bordered table-hover">
				<thead>
					<tr>
						<th>${__("Checklist")}</th>
						<th>${__("Status")}</th>
						<th>${__("Completion")}</th>
					</tr>
				</thead>
				<tbody>
					${rows}
				</tbody>
			</table>
		</div>
	`;
}