// Copyright (c) 2026, phamos.eu and contributors
// Event Ticket Order: one order of the website with its tickets (phamos/phamos#1717). The status follows the
// tickets; Customer and Sales Order are created from here (phamos/phamos#1725).

frappe.ui.form.on("Event Ticket Order", {
	refresh(frm) {
		frm.disable_save();
		if (frm.doc.status === "Booked") {
			frm.add_custom_button(__("Create Sales Order"), () => phamos_ticket_order.create_sales_order(frm));
		}
		if (frm.doc.status === "Ordered") {
			frm.add_custom_button(__("Create Sales Invoice"), () => phamos_ticket_order.create_sales_invoice(frm));
		}
	},
});

const phamos_ticket_order = {
	create_sales_order(frm) {
		frappe.call({
			method: "phamos.marketing.api.order_customer_proposal",
			args: { name: frm.doc.name },
		}).then(({ message: proposal }) => this.customer_dialog(frm, proposal));
	},

	// The Customer, following the buyer's link: nothing is used or converted without this dialog.
	customer_dialog(frm, proposal) {
		const esc = frappe.utils.escape_html;
		const choices = [];
		if (proposal.customer) {
			choices.push({ value: "use", label: __("Use Customer {0}", [esc(proposal.customer_name || proposal.customer)]) });
		} else if (proposal.lead) {
			choices.push({ value: "convert", label: __("Convert Lead {0} into a Customer", [esc(proposal.lead_name || proposal.lead)]) });
		}
		choices.push({ value: "other", label: __("Choose another Customer") });
		if (!proposal.lead || proposal.customer) {
			choices.push({ value: "new", label: __("Create a new Customer from the billing data") });
		}
		const similar = (proposal.matches || []).map((m) => esc(m.customer_name)).join(", ");
		const dialog = new frappe.ui.Dialog({
			title: __("Create Sales Order"),
			fields: [
				{ fieldname: "choice", fieldtype: "Select", label: __("Customer"), options: choices, default: choices[0].value,
					reqd: 1, description: similar ? __("Customers with a similar name: {0}", [similar]) : "" },
				{ fieldname: "customer", fieldtype: "Link", options: "Customer", label: __("Customer"),
					depends_on: "eval:doc.choice === 'other'", mandatory_depends_on: "eval:doc.choice === 'other'" },
			],
			primary_action_label: __("Create Sales Order"),
			primary_action: ({ choice, customer }) => {
				const args = { names: [frm.doc.name] };
				if (choice === "use") Object.assign(args, { mode: "use", customer: proposal.customer });
				else if (choice === "other") Object.assign(args, { mode: "use", customer });
				else args.mode = choice;
				frappe.call({ method: "phamos.marketing.api.create_order_sales_orders", args, freeze: true })
					.then(({ message }) => {
						dialog.hide();
						frappe.show_alert({ message: __("Sales Order {0} created", [message.sales_orders[0]]), indicator: "green" });
						frm.reload_doc();
					});
			},
		});
		dialog.show();
	},

	create_sales_invoice(frm) {
		frappe.call({
			method: "phamos.marketing.api.create_sales_invoices",
			args: { ticket_orders: [frm.doc.name] },
			freeze: true,
		}).then(({ message }) => {
			frappe.show_alert({ message: __("Sales Invoice {0} created", [message.sales_invoices.join(", ")]), indicator: "green" });
			frm.reload_doc();
		});
	},
};
