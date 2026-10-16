// Marketing Content (event): attendee counts, attendee list and report, campaign, newsletter.

frappe.ui.form.on("Marketing Content", {
	refresh(frm) {
		if (frm.is_new()) return;

		frappe.call({ method: "phamos.marketing.api.attendee_summary", args: { event: frm.doc.name } }).then((r) => {
			const c = r.message || {};
			frm.dashboard.add_indicator(__("Registered: {0}", [c.registered || 0]), "blue");
			frm.dashboard.add_indicator(__("Paid: {0}", [c.paid || 0]), "green");
			if (c.open_payment) frm.dashboard.add_indicator(__("Payment open: {0}", [c.open_payment]), "orange");
			if (c.attended || c.no_show) frm.dashboard.add_indicator(__("Attended: {0} · No show: {1}", [c.attended || 0, c.no_show || 0]), "gray");
		});

		frm.add_custom_button(__("Attendees"), () => frappe.set_route("List", "Attendee", { event: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Event Attendees Report"), () =>
			frappe.set_route("query-report", "Event Attendees", { event: frm.doc.name }), __("View"));
		frm.add_custom_button(__("Add Attendee"), () =>
			frappe.new_doc("Attendee", { event: frm.doc.name, source: "Manual" }), __("Create"));
		if (!frm.doc.campaign) {
			frm.add_custom_button(__("Campaign"), () =>
				frappe.call({ method: "phamos.marketing.api.create_campaign", args: { event: frm.doc.name } })
					.then(() => frm.reload_doc()), __("Create"));
		}
		frm.add_custom_button(__("Newsletter"), () => {
			if (!frm.doc.email_group) {
				frappe.msgprint({ title: __("Email Group Required"), indicator: "orange",
					message: __("Please set an Email Group on this record before creating a Newsletter.") });
				return;
			}
			frappe.call({
				method: "phamos.marketing.doctype.marketing_content.marketing_content.create_newsletter_for_event",
				args: { event_name: frm.doc.name },
			}).then((r) => r.message && frappe.set_route("Form", "Newsletter", r.message));
		}, __("Create"));
	},
});
