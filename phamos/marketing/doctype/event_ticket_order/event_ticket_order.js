// Copyright (c) 2026, phamos.eu and contributors
// Event Ticket Order: one order of the website or the desk with its tickets (phamos/phamos#1717). The status
// follows the tickets; Customer and Sales Order are created from here (phamos/phamos#1725). Desk orders are
// edited here until the Sales Order (phamos/phamos#1730).

frappe.ui.form.on("Event Ticket Order", {
	refresh(frm) {
		const editable = phamos_ticket_order.editable(frm);
		if (!editable) frm.disable_save();
		phamos_ticket_order.load_prices(frm, frm.is_new());
		if (frm.is_new()) return;
		if (editable) {
			// Follow-up documents under "Create", as in ERPNext (phamos/phamos#1730).
			frm.add_custom_button(__("Attendee"), () => phamos_ticket_order.new_attendee(frm), __("Create"));
		}
		if (frm.doc.status === "Booked") {
			frm.add_custom_button(__("Sales Order"), () => phamos_ticket_order.create_sales_order(frm), __("Create"));
		}
		if (frm.doc.status === "Ordered") {
			frm.add_custom_button(__("Sales Invoice"), () => phamos_ticket_order.create_sales_invoice(frm), __("Create"));
		}
	},

	event(frm) {
		frm.set_value("ticket_type", "");
		frm.set_value("ticket_rate", 0);
		phamos_ticket_order.load_prices(frm, true);
	},

	// The rate of the chosen price row; it can still be changed by hand.
	ticket_type(frm) {
		const row = (frm.__ticket_prices || []).find((r) => r.title === frm.doc.ticket_type);
		if (row) frm.set_value("ticket_rate", row.rate);
	},
});

const phamos_ticket_order = {
	editable(frm) {
		return frm.doc.source === "Desk" && ["Booked", "Free"].includes(frm.doc.status);
	},

	// The event's price rows as the choices of "Price" (desk orders only); ``prefill``: the row that applies now.
	load_prices(frm, prefill) {
		if (!this.editable(frm) || !frm.doc.event) return;
		frappe.call({
			method: "phamos.marketing.doctype.event_ticket_order.event_ticket_order.ticket_prices",
			args: { event: frm.doc.event },
		}).then(({ message }) => {
			frm.__ticket_prices = message.prices;
			frm.set_df_property("ticket_type", "options", message.prices.map((r) => r.title));
			frm.toggle_display(["ticket_type", "ticket_rate"], message.paid);
			if (prefill && message.current && !frm.doc.ticket_type) frm.set_value("ticket_type", message.current);
		});
	},

	new_attendee(frm) {
		frappe.new_doc("Attendee", {
			event: frm.doc.event,
			event_ticket_order: frm.doc.name,
			ticket_type: frm.doc.ticket_type || "Free",
			company_name: frm.doc.billing_company,
			language: frm.doc.language,
		});
	},

	create_sales_order(frm) {
		frappe.call({
			method: "phamos.marketing.api.order_customer_proposal",
			args: { name: frm.doc.name },
		}).then(({ message: proposal }) => {
			if (proposal.sales_order) frappe.set_route("Form", "Sales Order", proposal.sales_order);
			else this.customer_dialog(frm, proposal);
		});
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
						// A draft, to be checked and submitted by hand (phamos/phamos#1730).
						frappe.set_route("Form", "Sales Order", message.sales_orders[0]);
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
