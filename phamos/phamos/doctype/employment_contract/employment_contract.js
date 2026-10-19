// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employment Contract", {
	setup(frm) {
		frm.set_query("expense_account", () => ({
			filters: { company: frm.doc.company, root_type: "Expense", is_group: 0 },
		}));
	},

	refresh(frm) {
		render_history(frm);

		const can_change =
			frm.doc.docstatus === 1 &&
			["Active", "Upcoming"].includes(frm.doc.status) &&
			!frm.doc.superseded_by &&
			frappe.model.can_create("Employment Contract");
		if (can_change) {
			frm.add_custom_button(__("Record Change"), () => record_change(frm)).addClass("btn-primary");
		}

		if (frm.is_new() && frm.doc.__change_of) {
			frm.set_intro(
				__("Recording a change to {0}. Set the date it takes effect and the new terms.", [
					frm.doc.__change_of,
				]),
				"blue"
			);
			setTimeout(() => frm.get_field("effective_from").$input?.focus(), 300);
		}
	},

	fte_percentage: (frm) => calculate(frm),
	full_time_hours_per_week: (frm) => calculate(frm),
	yearly_gross_full_time: (frm) => calculate(frm),
	monthly_amount: (frm) => calculate(frm),
	contract_type: (frm) => calculate(frm),
	conversion_rate: (frm) => calculate(frm),
	working_days_per_week: (frm) => calculate(frm),
	full_time_leave_days: (frm) => calculate(frm),
	valid_until: (frm) => calculate(frm),
	company(frm) {
		frm.set_value("expense_account", null);
		set_planning_rate(frm, true);
	},
	currency(frm) {
		set_planning_rate(frm, true);
	},
	effective_from(frm) {
		calculate(frm);
		// Keep a rate the user typed; only fill one that is still empty.
		set_planning_rate(frm, false);
	},
	employee(frm) {
		render_history(frm);
	},
});

// Preview of the derived values; the server recomputes them on save.
function calculate(frm) {
	const fte = flt(frm.doc.fte_percentage);
	frm.set_value("weekly_hours", (fte * flt(frm.doc.full_time_hours_per_week)) / 100);
	const monthly =
		frm.doc.contract_type === "External"
			? flt(frm.doc.monthly_amount)
			: (flt(frm.doc.yearly_gross_full_time) * fte) / 100 / 12;
	frm.set_value("monthly_gross", monthly);
	frm.set_value("base_monthly_gross", monthly * (flt(frm.doc.conversion_rate) || 1));

	if (frm.doc.contract_type === "External") return;
	const yearly = round_leave_days(
		(flt(frm.doc.full_time_leave_days) * flt(frm.doc.working_days_per_week)) / 5
	);
	frm.set_value("leave_days_per_year", yearly);
	frm.set_value("leave_days_for_period", prorate_leave_days(yearly, frm.doc.effective_from, frm.doc.valid_until));
}

// Same rules as prorate_leave_days and round_leave_days in employment_contract.py.
function prorate_leave_days(yearly, effective_from, valid_until) {
	if (!valid_until || !effective_from) return yearly;
	// Count like relativedelta, not moment's diff: moment anchors on month ends.
	const to_date = (value) => {
		const [y, m, d] = value.split("-").map(Number);
		return new Date(y, m - 1, d);
	};
	const start = to_date(effective_from);
	// Valid Until is the last day of the contract, so full months run up to the day after.
	const end = to_date(valid_until);
	end.setDate(end.getDate() + 1);
	let months = (end.getFullYear() - start.getFullYear()) * 12 + (end.getMonth() - start.getMonth());
	if (end.getDate() < start.getDate()) months -= 1;
	return months >= 12 ? yearly : round_leave_days((yearly * Math.max(months, 0)) / 12);
}

function round_leave_days(days) {
	const whole = Math.floor(days + 1e-9);
	return days - whole >= 0.5 - 1e-9 ? whole + 1 : flt(days, 2);
}

// Default planning rate from Currency Exchange; the server keeps it fixed once saved.
function set_planning_rate(frm, replace) {
	if (frm.doc.docstatus !== 0 || !frm.doc.company || !frm.doc.currency) return;
	if (!replace && flt(frm.doc.conversion_rate)) return;
	frappe
		.xcall(
			"phamos.phamos.doctype.employment_contract.employment_contract.get_planning_exchange_rate",
			{ currency: frm.doc.currency, company: frm.doc.company, on_date: frm.doc.effective_from }
		)
		.then(({ company_currency, rate }) => {
			frm.set_value("company_currency", company_currency);
			frm.set_value("conversion_rate", rate || null);
			calculate(frm);
		});
}

// A change is a new contract with the same terms; the user only sets the date and what differs.
function record_change(frm) {
	const doc = frappe.model.copy_doc(frm.doc);
	doc.effective_from = null;
	doc.valid_until = null;
	// A new contract takes the planning rate of its own start date.
	if (doc.currency !== doc.company_currency) doc.conversion_rate = null;
	doc.__change_of = frm.doc.name;
	frappe.set_route("Form", doc.doctype, doc.name);
}

function render_history(frm) {
	const field = frm.get_field("contract_history");
	if (!field || frm.is_new() || !frm.doc.employee) return;

	frappe
		.xcall(
			"phamos.phamos.doctype.employment_contract.employment_contract.get_contract_history",
			{ employee: frm.doc.employee }
		)
		.then((rows) => {
			if (!rows.length) {
				field.$wrapper.html("");
				return;
			}
			const cell = (value, type, currency) =>
				frappe.format(value, { fieldtype: type, options: currency }, { inline: true });
			const body = rows
				.map((row) => {
					const current = row.name === frm.doc.name;
					const period = `${cell(row.effective_from, "Date")} – ${
						row.valid_until ? cell(row.valid_until, "Date") : __("open")
					}`;
					return `<tr class="${current ? "contract-history-current" : ""}">
						<td><a href="/app/employment-contract/${encodeURIComponent(row.name)}">${frappe.utils.escape_html(row.name)}</a></td>
						<td>${period}</td>
						<td>${__(row.contract_type)}</td>
						<td class="text-right">${cell(row.fte_percentage, "Percent")}</td>
						<td class="text-right">${cell(row.weekly_hours, "Float")}</td>
						<td class="text-right">${cell(row.monthly_gross, "Currency", row.currency)}</td>
						<td>${__(row.status)}</td>
					</tr>`;
				})
				.join("");
			field.$wrapper.html(`
				<style>
					.contract-history td, .contract-history th { padding: var(--padding-xs) var(--padding-sm); }
					.contract-history .contract-history-current td { background: var(--subtle-fg); font-weight: var(--weight-semibold); }
				</style>
				<table class="table table-sm contract-history">
					<thead><tr>
						<th>${__("Contract")}</th><th>${__("Period")}</th><th>${__("Type")}</th>
						<th class="text-right">${__("FTE %")}</th><th class="text-right">${__("Weekly Hours")}</th>
						<th class="text-right">${__("Monthly Gross")}</th><th>${__("Status")}</th>
					</tr></thead>
					<tbody>${body}</tbody>
				</table>`);
		});
}
