frappe.ui.form.on("Phriend Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test GitLab Connection"), () => {
			frappe.call({
				method: "phamos.phriend.api.test_gitlab_connection",
				freeze: true,
				freeze_message: __("Asking GitLab..."),
				callback: (r) => {
					if (r.message) {
						frappe.msgprint({
							title: __("GitLab connection works"),
							indicator: "green",
							message: __("Connected to {0}", [
								`<a href="${r.message.web_url}" target="_blank">${frappe.utils.escape_html(
									r.message.name_with_namespace
								)}</a>`,
							]),
						});
					}
				},
			});
		});
	},
});
