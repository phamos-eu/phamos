// Phriend buttons on Issue: triage a report into GitLab, or jump back to the page.

frappe.ui.form.on("Issue", {
	phriend_screenshot(frm) {
		phriend_render_preview(frm);
	},

	refresh(frm) {
		if (frm.is_new() || !frm.doc.phriend_type) return;

		phriend_render_preview(frm);

		if (frm.doc.phriend_page_url) {
			frm.add_custom_button(
				__("Open Reported Page"),
				() => window.open(frm.doc.phriend_page_url, "_blank"),
				__("Phriend")
			);
		}

		if (frm.doc.gitlab_issue_url) {
			frm.add_custom_button(__("Open in GitLab"), () => window.open(frm.doc.gitlab_issue_url, "_blank"));
		} else {
			frm.add_custom_button(__("Create GitLab Issue"), () => phriend_create_gitlab_issue(frm)).addClass(
				"btn-primary"
			);
		}
	},
});

function phriend_render_preview(frm) {
	const field = frm.get_field("phriend_screenshot_preview");
	if (!field) return;
	const url = frm.doc.phriend_screenshot;
	field.$wrapper.html(
		url
			? `<div class="form-group">
				<label class="control-label">${__("Screenshot")}</label>
				<a href="${encodeURI(url)}" target="_blank" title="${__("Open full size")}">
					<img src="${encodeURI(url)}" alt="${__("Screenshot")}"
						style="max-width: 100%; border: 1px solid var(--border-color); border-radius: var(--border-radius-md);">
				</a>
			</div>`
			: `<div class="form-group">
				<label class="control-label">${__("Screenshot")}</label>
				<p class="text-muted small">${__("No screenshot was captured for this report.")}</p>
			</div>`
	);
}

function phriend_create_gitlab_issue(frm) {
	frappe.call("phamos.phriend.api.get_gitlab_defaults").then(({ message: defaults }) => {
		if (!defaults.has_token) {
			frappe.msgprint({
				title: __("GitLab not set up"),
				indicator: "orange",
				message: __("Add a GitLab token in {0} or {1} first.", [
					`<a href="/app/phriend-settings">${__("Phriend Settings")}</a>`,
					`<a href="/app/gitlab-settings">${__("GitLab Settings")}</a>`,
				]),
			});
			return;
		}

		const dialog = new frappe.ui.Dialog({
			title: __("Create GitLab Issue"),
			fields: [
				{
					fieldtype: "Data",
					fieldname: "title",
					label: __("Issue Title"),
					reqd: 1,
					default: frm.doc.subject,
				},
				{
					fieldtype: "HTML",
					fieldname: "where",
					options: `<p class="text-muted small">${__("Will be created in {0}", [
						`<b>${frappe.utils.escape_html(defaults.gitlab_project)}</b>`,
					])}</p>`,
				},
				{
					fieldtype: "Data",
					fieldname: "labels",
					label: __("Labels"),
					default: defaults.gitlab_labels,
					description: __("Comma separated"),
				},
			],
			primary_action_label: __("Create Issue"),
			primary_action(values) {
				dialog.disable_primary_action();
				frappe.call({
					method: "phamos.phriend.api.create_gitlab_issue",
					args: { issue: frm.doc.name, title: values.title, labels: values.labels },
					freeze: true,
					freeze_message: __("Sending to GitLab..."),
					callback(r) {
						if (!r.message) return;
						dialog.hide();
						frappe.show_alert(
							{
								message: __("GitLab issue #{0} created", [r.message.iid]),
								indicator: "green",
							},
							6
						);
						frm.reload_doc();
					},
					always: () => dialog.enable_primary_action(),
				});
			},
		});
		dialog.show();
	});
}
