// The Issue Assistant's e-mail drafts to the reporter (#2229): shown on the Issue and sent with Frappe's
// usual e-mail dialog, filled from the draft. The chat links to /app/issue/<name>?draft=<draft>, which
// opens that draft right away. A confidentiality check warns in the dialog; it does not block Send.
frappe.ui.form.on("Issue", {
	refresh(frm) {
		if (frm.is_new()) return;
		issue_drafts_load(frm);
	},
});

const ISSUE_DRAFTS_CHECK = "phamos.ai_agents.agents.issue_drafts.check_email";

function issue_drafts_load(frm) {
	frappe
		.xcall("phamos.ai_agents.agents.issue_drafts.get_drafts", { issue: frm.doc.name })
		.then((drafts) => {
			frm.issue_drafts = drafts || [];
			frm.remove_custom_button(__("E-mail draft"));
			// Frappe shows the headline in the form layout's message area, not in the dashboard
			const message = $(frm.layout.message);
			if (!frm.issue_drafts.length) {
				if (message.find(".issue-draft-open").length) frm.dashboard.clear_headline();
				return;
			}
			const label =
				frm.issue_drafts.length === 1
					? __("The Issue Assistant prepared an e-mail draft to the reporter. It is not sent yet.")
					: __("The Issue Assistant prepared {0} e-mail drafts to the reporter. They are not sent yet.", [
							frm.issue_drafts.length,
					  ]);
			frm.dashboard.set_headline_alert(
				`<div class="row"><div class="col-xs-12">${label}
					<a href="#" class="issue-draft-open">${__("Review and send")}</a> ·
					<a href="#" class="issue-draft-discard text-muted">${__("Discard draft")}</a></div></div>`,
				"orange"
			);
			message.find(".issue-draft-open").on("click", (e) => {
				e.preventDefault();
				issue_drafts_open(frm, frm.issue_drafts[0]);
			});
			message.find(".issue-draft-discard").on("click", (e) => {
				e.preventDefault();
				issue_drafts_discard(frm, frm.issue_drafts[0]);
			});
			frm.add_custom_button(__("E-mail draft"), () => issue_drafts_open(frm, frm.issue_drafts[0])).addClass(
				"btn-primary"
			);
			const wanted = frappe.utils.get_url_arg("draft");
			const draft = wanted && frm.issue_drafts.find((d) => d.name === wanted);
			if (draft && !frm.issue_draft_opened) {
				frm.issue_draft_opened = true;
				issue_drafts_open(frm, draft);
			}
		});
}

function issue_drafts_discard(frm, draft) {
	frappe.confirm(__("Discard this e-mail draft?"), () =>
		frappe
			.xcall("phamos.ai_agents.agents.issue_drafts.discard_draft", { name: draft.name })
			.then(() => issue_drafts_load(frm))
	);
}

function issue_drafts_open(frm, draft) {
	const composer = new frappe.views.CommunicationComposer({
		doc: frm.doc,
		frm: frm,
		title: __("E-mail draft by the Issue Assistant"),
		recipients: draft.recipients,
		cc: draft.cc || "",
		// drafts from before #2229's subject rule: Frappe's identifier threads the answer back
		subject: draft.subject.includes(`#${frm.doc.name}`) ? draft.subject : `${draft.subject} (#${frm.doc.name})`,
		message: draft.content,
		success() {
			// sent the usual way: the draft has done its job
			frappe
				.xcall("phamos.ai_agents.agents.issue_drafts.discard_draft", { name: draft.name })
				.then(() => issue_drafts_load(frm));
		},
	});
	const dialog = composer.dialog;
	const warning = $(`<div class="alert alert-danger small issue-draft-warning hidden"></div>`).prependTo(
		dialog.$body
	);
	const values = () => {
		const v = dialog.get_values(true) || {};
		return {
			issue: frm.doc.name,
			subject: v.subject || "",
			content: composer.get_email_content ? composer.get_email_content() : v.content || "",
			recipients: v.recipients || "",
			cc: v.cc || "",
		};
	};
	const show = (problems) => {
		if (!problems.length) {
			warning.addClass("hidden").empty();
			return;
		}
		warning
			.removeClass("hidden")
			.html(
				`<b>${__("Please check before sending:")}</b><ul class="mb-0">${problems
					.map((p) => `<li>${frappe.utils.escape_html(p)}</li>`)
					.join("")}</ul>`
			);
	};
	// the draft as written by the assistant, checked right away
	frappe
		.xcall(ISSUE_DRAFTS_CHECK, {
			issue: frm.doc.name,
			subject: draft.subject,
			content: draft.content,
			recipients: draft.recipients,
			cc: draft.cc || "",
		})
		.then(show);
	// and again on Send, with the edits: a warning asks once, it never blocks
	const send = composer.send_action.bind(composer);
	composer.send_action = () =>
		frappe.xcall(ISSUE_DRAFTS_CHECK, values()).then((problems) => {
			show(problems);
			if (!problems.length) return send();
			frappe.confirm(
				`${__("This e-mail may not be meant for this customer:")}<ul>${problems
					.map((p) => `<li>${frappe.utils.escape_html(p)}</li>`)
					.join("")}</ul>${__("Send it anyway?")}`,
				send
			);
		});
}
