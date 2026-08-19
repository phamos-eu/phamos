// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.query_reports["Employee Upcoming Birthday"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
	],
};
