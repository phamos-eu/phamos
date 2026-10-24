// Copyright (c) 2026, phamos.eu and contributors
// Attendee: CRM link, order and attendance actions (phamos.marketing.api).

const ATTENDEE_API = "phamos.marketing.api";

frappe.ui.form.on("Attendee", {
	refresh(frm) {
		if (frm.is_new()) return;
		const group = __("Actions");
		frm.add_custom_button(__("Link to CRM"), () => phamos_attendee.link_to_crm(frm), group);
		if (!frm.doc.sales_order && frm.doc.payment_status !== "Not Required") {
			frm.add_custom_button(__("Create Sales Order"), () => phamos_attendee.create_sales_order(frm), group);
		}
		if (frm.doc.sales_order && !frm.doc.sales_invoice) {
			frm.add_custom_button(__("Create Sales Invoice"), () =>
				phamos_attendee.call("create_sales_invoices", { names: [frm.doc.name] }, frm), group);
		}
		if (!frm.doc.opportunity && (frm.doc.customer || frm.doc.lead)) {
			frm.add_custom_button(__("Create Opportunity"), () =>
				phamos_attendee.call("create_opportunities", { names: [frm.doc.name] }, frm), group);
		}
		if (frm.doc.email) {
			frm.add_custom_button(__("Send Ticket"), () =>
				frappe.call({ method: `${ATTENDEE_API}.send_ticket`, args: { name: frm.doc.name }, freeze: true })
					.then((r) => frappe.show_alert({ message: __("Ticket sent to {0}", [r.message.sent_to]), indicator: "green" })),
				group);
		}
		for (const status of ["Attended", "No Show"]) {
			if (frm.doc.status !== status) {
				frm.add_custom_button(__(status), () =>
					phamos_attendee.call("set_attendance", { names: [frm.doc.name], status }, frm), __("Attendance"));
			}
		}
		if (frm.doc.payment_status) {
			frm.dashboard.add_indicator(__("Payment: {0}", [__(frm.doc.payment_status)]),
				phamos_attendee.payment_colour(frm.doc.payment_status));
		}
	},
});

window.phamos_attendee = {
	payment_colour(status) {
		return { Paid: "green", Credited: "purple", Invoiced: "orange", Ordered: "blue", Pending: "red",
			Cancelled: "gray", "Not Required": "gray" }[status] || "gray";
	},

	call(method, args, frm) {
		return frappe.call({ method: `${ATTENDEE_API}.${method}`, args, freeze: true }).then((r) => {
			const m = r.message || {};
			const docs = m.sales_orders || m.sales_invoices || m.opportunities || [];
			frappe.show_alert({ message: docs.length ? __("Created: {0}", [docs.join(", ")]) : __("Done"), indicator: "green" });
			frm ? frm.reload_doc() : cur_list && cur_list.refresh();
			return m;
		});
	},

	link_to_crm(frm) {
		frappe.call({ method: `${ATTENDEE_API}.crm_matches`, args: { name: frm.doc.name } }).then((r) => {
			const m = r.message || {};
			const lines = [];
			if (m.customer) lines.push(__("Customer by email: {0}", [m.customer]));
			if (m.contact) lines.push(__("Contact: {0}", [m.contact]));
			if (m.lead) lines.push(__("Lead: {0}", [m.lead]));
			(m.suggestions || []).forEach((s) => lines.push(__("Company match ({0} %): {1}", [s.score, s.customer_name])));
			if (!lines.length) lines.push(__("Nothing found: a new Lead and Contact will be created."));
			const d = new frappe.ui.Dialog({
				title: __("Link {0} to the CRM", [frm.doc.full_name]),
				fields: [
					{ fieldtype: "HTML", options: `<p>${lines.map(frappe.utils.escape_html).join("<br>")}</p>` },
					{ fieldname: "customer", fieldtype: "Link", options: "Customer", label: __("Belongs to Customer"),
						default: m.customer || (m.suggestions || [])[0]?.customer,
						description: __("Leave empty to link the person as Lead.") },
				],
				primary_action_label: __("Link"),
				primary_action(values) {
					d.hide();
					phamos_attendee.call("link_to_crm", { names: [frm.doc.name], customer: values.customer || null }, frm);
				},
			});
			d.show();
		});
	},

	create_sales_order(frm) {
		frappe.prompt([
			{ fieldname: "customer", fieldtype: "Link", options: "Customer", label: __("Customer"),
				default: frm.doc.billing_customer || frm.doc.customer,
				description: __("Empty: the Customer of the order's buyer.") },
			{ fieldname: "submit", fieldtype: "Check", label: __("Submit right away") },
		], (values) => phamos_attendee.call("create_sales_orders",
			{ names: [frm.doc.name], customer: values.customer || null, submit: values.submit }, frm),
		__("Create Sales Order"), __("Create"));
	},
};
