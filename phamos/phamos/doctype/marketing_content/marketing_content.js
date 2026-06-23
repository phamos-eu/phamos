frappe.ui.form.on('Marketing Content', {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__('Create Newsletter'), function () {
				if (!frm.doc.email_group) {
					frappe.msgprint({
						title: __('Email Group Required'),
						message: __('Please set an Email Group on this record before creating a Newsletter.'),
						indicator: 'orange'
					});
					return;
				}

				frappe.call({
					method: 'phamos.phamos.doctype.marketing_content.marketing_content.create_newsletter_for_event',
					args: { event_name: frm.doc.name },
					callback(r) {
						if (r.message) {
							frappe.set_route('Form', 'Newsletter', r.message);
						}
					}
				});
			});
		}
	}
});
