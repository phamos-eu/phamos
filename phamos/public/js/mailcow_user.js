frappe.ui.form.on("User", {
	refresh: function (frm) {
		frm.trigger("set_custom_buttons");
	},

	set_custom_buttons: function (frm) {
		// frm.reload_doc();
		if (!frm.is_new()) {
			frm.add_custom_button(__('Generate DAV Password'), () => {
				frappe.call({
					method: "phamos.mailcow_integration.dav_password.generate_dav_password",
					args: {
                        username: frm.doc.name,
                    },
					callback(r){
						if (r.message && r.message.status == "ok") { 
							frappe.msgprint("DAV Password Generated Successfully!");
						}
					}
				})
				// frm.reload_doc();

			}, __("Mailcow"));

		}
	},

	
});