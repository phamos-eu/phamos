// The Issue Assistant's e-mail drafts to the reporter (#2229): shown on the Issue, reviewed and sent
// here. The chat links to /app/issue/<name>?draft=<draft>, which opens that draft right away.
frappe.ui.form.on("Issue", {
	refresh(frm) {
		if (frm.is_new()) return;
		issue_drafts_load(frm);
	},
});

function issue_drafts_load(frm) {
	frappe
		.xcall("phamos.ai_agents.agents.issue_drafts.get_drafts", { issue: frm.doc.name })
		.then((drafts) => {
			frm.issue_drafts = drafts || [];
			frm.remove_custom_button(__("E-mail draft"));
			if (!frm.issue_drafts.length) return;
			const label =
				frm.issue_drafts.length === 1
					? __("The Issue Assistant prepared an e-mail draft to the reporter. It is not sent yet.")
					: __("The Issue Assistant prepared {0} e-mail drafts to the reporter. They are not sent yet.", [
							frm.issue_drafts.length,
					  ]);
			frm.dashboard.set_headline_alert(
				`<div class="row"><div class="col-xs-12">${label} <a class="issue-draft-open">${__("Review and send")}</a></div></div>`,
				"orange"
			);
			frm.dashboard.wrapper.find(".issue-draft-open").on("click", () => issue_drafts_open(frm, frm.issue_drafts[0]));
			frm.add_custom_button(__("E-mail draft"), () => issue_drafts_open(frm, frm.issue_drafts[0])).addClass("btn-primary");
			const wanted = frappe.utils.get_url_arg("draft");
			const draft = wanted && frm.issue_drafts.find((d) => d.name === wanted);
			if (draft && !frm.issue_draft_opened) {
				frm.issue_draft_opened = true;
				issue_drafts_open(frm, draft);
			}
		});
}

function issue_drafts_open(frm, draft) {
	const values = () => {
		const v = dialog.get_values();
		return { name: draft.name, subject: v.subject, content: v.content, recipients: v.recipients, cc: v.cc || "" };
	};
	const dialog = new frappe.ui.Dialog({
		title: __("E-mail draft – not sent"),
		size: "large",
		fields: [
			{ fieldname: "recipients", fieldtype: "Data", label: __("To"), reqd: 1, default: draft.recipients },
			{ fieldname: "cc", fieldtype: "Data", label: __("CC"), default: draft.cc || "" },
			{ fieldname: "subject", fieldtype: "Data", label: __("Subject"), reqd: 1, default: draft.subject },
			{ fieldname: "content", fieldtype: "Text Editor", label: __("Message"), default: draft.content },
			{
				fieldname: "hint",
				fieldtype: "HTML",
				options: `<p class="text-muted small">${__(
					"Your signature is added when you send. Recipients must be contacts of this Issue's customer."
				)}</p>`,
			},
		],
		primary_action_label: __("Send"),
		primary_action() {
			frappe
				.xcall("phamos.ai_agents.agents.issue_drafts.send_draft", values())
				.then(() => {
					dialog.hide();
					frappe.show_alert({ message: __("E-mail sent"), indicator: "green" });
					frm.reload_doc();
				});
		},
		secondary_action_label: __("Save draft"),
		secondary_action() {
			frappe.xcall("phamos.ai_agents.agents.issue_drafts.save_draft", values()).then(() => {
				frappe.show_alert({ message: __("Draft saved"), indicator: "blue" });
				dialog.hide();
				issue_drafts_load(frm);
			});
		},
	});
	dialog.add_custom_action(
		__("Discard"),
		() =>
			frappe.confirm(__("Discard this e-mail draft?"), () =>
				frappe.xcall("phamos.ai_agents.agents.issue_drafts.discard_draft", { name: draft.name }).then(() => {
					dialog.hide();
					issue_drafts_load(frm);
					frm.dashboard.clear_headline();
				})
			),
		"btn-danger"
	);
	dialog.show();
}
