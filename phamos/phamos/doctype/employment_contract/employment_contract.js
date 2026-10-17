// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

// Preview of the derived values; the server recomputes them on save.
frappe.ui.form.on("Employment Contract", {
	setup(frm) {
		frm.set_query("expense_account", () => ({
			filters: { company: frm.doc.company, root_type: "Expense", is_group: 0 },
		}));
	},
	fte_percentage: (frm) => calculate(frm),
	full_time_hours_per_week: (frm) => calculate(frm),
	yearly_gross_full_time: (frm) => calculate(frm),
	monthly_amount: (frm) => calculate(frm),
	contract_type: (frm) => calculate(frm),
	company(frm) {
		frm.set_value("expense_account", null);
	},
});

function calculate(frm) {
	const fte = flt(frm.doc.fte_percentage);
	frm.set_value("weekly_hours", (fte * flt(frm.doc.full_time_hours_per_week)) / 100);
	const monthly =
		frm.doc.contract_type === "External"
			? flt(frm.doc.monthly_amount)
			: (flt(frm.doc.yearly_gross_full_time) * fte) / 100 / 12;
	frm.set_value("monthly_gross", monthly);
}
