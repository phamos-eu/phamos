// Phriend buttons on Issue: jump back to the reported page; any Issue can get GitLab issues,
// several if needed, listed in the "GitLab Issues" block (GitLab Issue records linked to it).

frappe.ui.form.on("Issue", {
	phriend_screenshot(frm) {
		phriend_render_preview(frm);
	},

	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.phriend_type) {
			phriend_render_preview(frm);
			if (frm.doc.phriend_page_url) {
				frm.add_custom_button(
					__("Open Reported Page"),
					() => window.open(frm.doc.phriend_page_url, "_blank"),
					__("Phriend")
				);
			}
		}

		const button = frm.add_custom_button(__("Create GitLab Issue"), () => phriend_create_gitlab_issue(frm));
		if (!frm.doc.gitlab_issue_url) button.addClass("btn-primary");
		phriend_render_gitlab_issues(frm);
	},
});

function phriend_render_gitlab_issues(frm) {
	const field = frm.get_field("phriend_gitlab_issues");
	if (!field || !frm.doc.gitlab_issue_url) return;
	const esc = frappe.utils.escape_html;
	const label = `<label class="control-label">${esc(__("GitLab Issues"))}</label>`;
	frappe.call("phamos.phriend.gitlab_issues.get_issue_gitlab", { issue: frm.doc.name }).then(({ message }) => {
		const rows = message || [];
		if (!rows.length) {
			field.$wrapper.html(
				`<div class="form-group">${label}<p class="text-muted small">${esc(
					__("Not linked as a record in ERPNext.")
				)} <a href="${encodeURI(frm.doc.gitlab_issue_url)}" target="_blank" rel="noopener">${esc(
					__("Open in GitLab")
				)}</a></p></div>`
			);
			return;
		}
		const items = rows
			.map((row) => {
				const closed = row.state === "closed";
				const state = `<span class="indicator-pill ${closed ? "gray" : "green"}">${esc(
					closed ? __("Closed") : __("Open")
				)}</span>`;
				const labels = row.labels
					.map((l) => `<span class="badge badge-light text-muted" style="font-weight: normal;">${esc(l)}</span>`)
					.join(" ");
				return `<li style="margin-bottom: var(--margin-sm);">
					<a href="${encodeURI(row.url)}" target="_blank" rel="noopener"><b>${esc(row.reference)}</b> ${esc(
					row.title
				)}</a>
					<div class="small" style="margin-top: 2px;">${state} ${labels}</div>
				</li>`;
			})
			.join("");
		field.$wrapper.html(
			`<div class="form-group">${label}<ul class="list-unstyled" style="margin: 0;">${items}</ul></div>`
		);
	});
}

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
								message: __("GitLab issue {0} created", [r.message.reference || `#${r.message.iid}`]),
								indicator: "green",
							},
							6
						);
						if (!r.message.gitlab_issue) {
							frappe.msgprint({
								title: __("GitLab issue not linked"),
								indicator: "orange",
								message: __(
									"The GitLab issue was created, but it is not linked to this Issue. Usually its project is not in ERPNext yet: run Sync Projects in {0} before the next one. Otherwise see the {1}.",
									[
										`<a href="/app/gitlab-settings">${__("GitLab Settings")}</a>`,
										`<a href="/app/error-log">${__("Error Log")}</a>`,
									]
								),
							});
						}
						frm.reload_doc();
					},
					always: () => dialog.enable_primary_action(),
				});
			},
		});
		dialog.show();
	});
}
