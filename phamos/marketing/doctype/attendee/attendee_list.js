// Attendee list: participation as indicator, bulk actions for the follow-up of an event.

frappe.listview_settings["Attendee"] = {
	add_fields: ["status", "payment_status", "vip", "role", "event"],
	get_indicator(doc) {
		const colours = { Invited: "gray", Registered: "blue", Confirmed: "blue", Waitlisted: "orange",
			Attended: "green", "No Show": "red", Cancelled: "gray" };
		return [__(doc.status), colours[doc.status] || "gray", `status,=,${doc.status}`];
	},
	formatters: {
		payment_status(value) {
			if (!value) return "";
			const colour = phamos_attendee_list_colour(value);
			return `<span class="indicator-pill ${colour} filterable" data-filter="payment_status,=,${value}">${__(value)}</span>`;
		},
		full_name(value, df, doc) {
			return doc.vip ? `${frappe.utils.escape_html(value)} <span class="indicator-pill yellow">VIP</span>` : frappe.utils.escape_html(value);
		},
	},
	onload(listview) {
		const api = "phamos.marketing.api";
		const run = (method, extra = {}) => {
			const names = listview.get_checked_items(true);
			if (!names.length) return frappe.msgprint(__("Please select attendees first."));
			frappe.call({ method: `${api}.${method}`, args: { names, ...extra }, freeze: true }).then((r) => {
				const m = r.message || {};
				const created = m.sales_orders || m.sales_invoices || m.opportunities || (m.results || []).map((x) => x.customer).filter(Boolean);
				frappe.msgprint(created && created.length ? __("Done: {0}", [created.join(", ")]) : __("Done"));
				if (m.skipped && m.skipped.length) frappe.show_alert(__("Skipped: {0}", [m.skipped.join(", ")]));
				listview.refresh();
			});
		};
		const group = __("Event Actions");
		listview.page.add_inner_button(__("Link to CRM"), () => run("link_to_crm"), group);
		listview.page.add_inner_button(__("Create Customer(s)"), () => run("create_customers"), group);
		listview.page.add_inner_button(__("Create Sales Order(s)"), () => run("create_sales_orders"), group);
		listview.page.add_inner_button(__("Create Sales Invoice(s)"), () => run("create_sales_invoices"), group);
		listview.page.add_inner_button(__("Create Opportunities"), () => run("create_opportunities"), group);
		listview.page.add_inner_button(__("Mark Attended"), () => run("set_attendance", { status: "Attended" }), group);
		listview.page.add_inner_button(__("Mark No Show"), () => run("set_attendance", { status: "No Show" }), group);
	},
};

function phamos_attendee_list_colour(status) {
	return { Paid: "green", Credited: "purple", Invoiced: "orange", Ordered: "blue", Pending: "red",
		Cancelled: "gray", "Not Required": "gray" }[status] || "gray";
}
