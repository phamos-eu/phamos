frappe.ui.form.on("Email Account", {
	refresh: function (frm) {
		if (frm.doc.enable_incoming && !frm.doc.__islocal) {
			frm.add_custom_button(__("Pull Emails"), function () {
				frappe.call({
					method: "phamos.api.pull_emails_now",
					args: { email_account: frm.doc.name },
					freeze: true,
					freeze_message: __("Fetching emails…"),
					callback: function (r) {
						if (r.exc) return;
						var res = r.message || {};
						if (res.ok === false) {
							frappe.msgprint({
								title: __("Email pull failed"),
								indicator: "red",
								message: "<pre style=\"white-space:pre-wrap;max-height:60vh;overflow:auto;\">" + frappe.utils.escape_html(res.error || "") + "</pre>",
							});
							return;
						}
						var changed = (res.changed_folders || []).length;
						var msg = changed
							? __("Pulled new emails from: {0}", [(res.changed_folders || []).join(", ")])
							: __("No new emails (nothing changed).");
						frappe.show_alert({ message: msg, indicator: changed ? "green" : "blue" }, 6);
					},
				});
			}, __("Actions"));
		}
	},
});
