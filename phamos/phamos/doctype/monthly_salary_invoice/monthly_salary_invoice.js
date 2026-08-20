// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

function set_items_amount_currency(frm) {
	if (!frm.fields_dict.items || !frm.fields_dict.items.grid) return;
	frm.fields_dict.items.grid.update_docfield_property("amount", "options", "currency");
	frm.refresh_field("items");
}

function recalculate_total_amount(frm) {
	if (!frm.fields_dict || !frm.fields_dict.total_amount) return;

	let total = 0;

	(frm.doc.items || []).forEach((row) => {
		total += flt(row.amount);
	});

	frm.set_value("total_amount", flt(total, 2));
}

frappe.ui.form.on("Monthly Salary Invoice", {
	setup(frm) {
		set_items_amount_currency(frm);

		frm.set_query("employee", () => {
			return {
				filters: {
					user_id: frappe.session.user
				}
			};
		});
	},

	refresh(frm) {
		set_items_amount_currency(frm);
		recalculate_total_amount(frm);
	},

	currency(frm) {
		set_items_amount_currency(frm);
		recalculate_total_amount(frm);
	},

	items_add(frm) {
		recalculate_total_amount(frm);
	},

	items_remove(frm) {
		recalculate_total_amount(frm);
	}
});

frappe.ui.form.on("Monthly Salary Invoice Item", {
	amount(frm) {
		recalculate_total_amount(frm);
	}
});