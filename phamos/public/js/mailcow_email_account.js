frappe.ui.form.on("Email Account", {
	refresh: function (frm) {
		frm.trigger("set_custom_buttons");
	},

	set_custom_buttons: function (frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__('Generate DAV Password'), () => {
				const username = frm.doc.email_id;

				if (!username) {
					frappe.msgprint(__('Email ID is required to generate DAV password.'));
					return;
				}

				frappe.call({
					method: "phamos.mailcow_integration.dav_password.generate_dav_password",
					args: {
						username: username,
					},
					callback(r) {
						if (r.message && r.message.status == "ok") {
							frappe.msgprint("DAV Password Generated Successfully!");
						}
					},
				});
			}, __("Mailcow"));
		}
	},
});
