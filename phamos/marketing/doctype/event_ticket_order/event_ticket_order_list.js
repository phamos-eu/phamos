// Copyright (c) 2026, phamos.eu and contributors

frappe.listview_settings["Event Ticket Order"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colour = { Free: "gray", Booked: "red", Ordered: "blue", Invoiced: "orange", Paid: "green",
			Credited: "purple", Cancelled: "gray" }[doc.status] || "gray";
		return [__(doc.status), colour, `status,=,${doc.status}`];
	},
	onload(listview) {
		const api = "phamos.marketing.api";
		const selected = () => {
			const names = listview.get_checked_items(true);
			if (!names.length) frappe.msgprint(__("Please select orders first."));
			return names;
		};
		const group = __("Order Actions");
		// Only orders whose Customer is unambiguous; the others are listed, to be done in the order (phamos/phamos#1725).
		listview.page.add_inner_button(__("Create Sales Order(s)"), () => {
			const names = selected();
			if (!names.length) return;
			frappe.call({ method: `${api}.create_order_sales_orders`, args: { names }, freeze: true }).then(({ message }) => {
				const lines = [message.sales_orders.length ? __("Done: {0}", [message.sales_orders.join(", ")]) : __("Done")];
				for (const row of message.skipped) {
					lines.push(`${frappe.utils.escape_html(row.order)}: ${frappe.utils.escape_html(row.reason)}`);
				}
				frappe.msgprint(lines.join("<br>"));
				listview.refresh();
			});
		}, group);
		listview.page.add_inner_button(__("Create Sales Invoice(s)"), () => {
			const ticket_orders = selected();
			if (!ticket_orders.length) return;
			frappe.call({ method: `${api}.create_sales_invoices`, args: { ticket_orders }, freeze: true }).then(({ message }) => {
				frappe.msgprint(message.sales_invoices.length ? __("Done: {0}", [message.sales_invoices.join(", ")]) : __("Done"));
				listview.refresh();
			});
		}, group);
	},
};
