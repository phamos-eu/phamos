frappe.ui.form.on("Issue", {
	refresh: function (frm) {
        if (!frm.doc.accounting_receipt) {
            frm.add_custom_button(__('Accounting Receipt'), () => {
                    frappe.call({
                        method: "phamos.phamos.doctype.accounting_receipt.accounting_receipt.make_accounting_receipt",
                        args: {
                            issue: frm.doc.name
                        },
                        callback(r){
                            frappe.set_route('Form', 'Accounting Receipt', r.message)
                        }
                    })
            }, __("Create"));
	    }
		phamos_add_open_in_cockpit(frm);
		phamos_add_issue_assistant_button(frm);
}
});

// "Open in Cockpit" (#1957): one entry per cockpit that can show this Issue, best fit first;
// each opens the cockpit's Issue page in a new tab. No fitting cockpit, no group.
function phamos_add_open_in_cockpit(frm) {
	if (frm.is_new()) return;
	const name = frm.doc.name;
	frappe.call({
		method: "phamos.api.issue_cockpits.get_issue_cockpits",
		args: { name },
		callback(r) {
			if (frm.doc.name !== name) return; // the form moved on while the call ran
			(r.message || []).forEach((cockpit) => {
				// Two refreshes of the same Issue can overlap; Frappe dedupes the toolbar entry
				// but not the mobile menu item, so drop any earlier copy first.
				frm.remove_custom_button(cockpit.label, __("Open in Cockpit"));
				frm.add_custom_button(
					cockpit.label,
					() => window.open(cockpit.url, "_blank", "noopener"),
					__("Open in Cockpit")
				);
			});
		},
	});
}

// Start the Issue Assistant by hand (testing): the dialog lists every check of the automatic
// start and of the AI gate with what would have to be set; starting is always possible, past a
// failing check it is a manual override and is recorded on the AI Agent Run.
function phamos_add_issue_assistant_button(frm) {
	if (frm.is_new() || !frm.has_perm("write")) return;
	frm.add_custom_button(__("Run Issue Assistant"), () => phamos_issue_assistant_dialog(frm));
}

function phamos_issue_assistant_dialog(frm) {
	frappe.call({
		method: "phamos.ai_agents.agents.issue.get_manual_run_info",
		args: { issue: frm.doc.name },
		callback(r) {
			const info = r.message;
			const failing = info.checks.filter((c) => !c.ok);
			const d = new frappe.ui.Dialog({
				title: __("Run Issue Assistant"),
				size: "large",
				fields: [{ fieldtype: "HTML", fieldname: "checks" }],
				primary_action_label: failing.length ? __("Start anyway") : __("Start"),
				primary_action() {
					d.disable_primary_action();
					frappe.call({
						method: "phamos.ai_agents.agents.issue.start_manual_run",
						args: { issue: frm.doc.name },
						callback(res) {
							d.hide();
							const out = res.message || {};
							if (!out.queued) {
								frappe.msgprint(
									out.reason === "already_running"
										? __("The Issue Assistant is already working on this Issue.")
										: __("The Issue Assistant could not start ({0}).", [out.reason])
								);
								return;
							}
							frappe.show_alert({
								message: out.manual_override
									? __("Issue Assistant started (manual override)")
									: __("Issue Assistant started"),
								indicator: "green",
							});
						},
						always() {
							d.enable_primary_action();
						},
					});
				},
			});
			d.fields_dict.checks.$wrapper.html(phamos_issue_assistant_checks_html(info));
			d.show();
		},
	});
}

function phamos_issue_assistant_checks_html(info) {
	const esc = frappe.utils.escape_html;
	const yes_no = (ok) =>
		`<span class="indicator-pill ${ok ? "green" : "red"}">${ok ? __("Yes") : __("No")}</span>`;
	const groups = {};
	info.checks.forEach((c) => (groups[c.group] = groups[c.group] || []).push(c));
	let html = `<div class="mb-3">
		<div>${__("Would start automatically for a new Issue")}: ${yes_no(info.would_start)}</div>
		<div class="mt-1">${__("May use the AI model")}: ${yes_no(info.model_allowed)}</div>
		<div class="text-muted small mt-2">${__(
			"The automatic start runs only when an Issue is created. Starting here always works; past a red check it is recorded as a manual override."
		)}</div>
	</div>`;
	Object.entries(groups).forEach(([group, checks]) => {
		html += `<h5 class="mt-3">${esc(group)}</h5>
		<table class="table table-bordered table-sm"><thead><tr>
			<th style="width:2em"></th><th>${__("Check")}</th><th>${__("Now")}</th><th>${__("Needed to pass")}</th>
		</tr></thead><tbody>`;
		checks.forEach((c) => {
			html += `<tr>
				<td>${c.ok ? "✅" : "❌"}</td>
				<td>${esc(c.label)}</td>
				<td>${esc(c.current)}</td>
				<td class="${c.ok ? "text-muted" : ""}">${esc(c.needed)}</td>
			</tr>`;
		});
		html += "</tbody></table>";
	});
	if (info.latest_run) {
		const run = info.latest_run;
		html += `<div class="text-muted small">${__("Last run")}:
			<a href="/app/ai-agent-run/${encodeURIComponent(run.name)}">${esc(run.name)}</a>
			· ${esc(__(run.status))} · ${esc(__(run.trigger))}${run.manual_override ? " · " + __("Manual Override") : ""}
			· ${esc(frappe.datetime.str_to_user(run.creation))}</div>`;
	}
	return html;
}
