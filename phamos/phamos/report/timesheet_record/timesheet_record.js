// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.query_reports["Timesheet Record"] = {
	"filters": [
		{
		"fieldname": "from_date",
		"label": "From Date",
		"fieldtype": "Date",
		"default": "Today"
		},
		{
		"fieldname": "to_date",
		"label": "To Date",
		"fieldtype": "Date",
		"default": "Today"
		},
		{
		"fieldname": "customer",
		"label": "Customer",
		"fieldtype": "Link",
		"options": "Customer"
		},
		{
		"fieldname": "employee",
		"label": "Employee",
		"fieldtype": "Link",
		"options": "Employee"
		}

	],
	formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (column.fieldname === "timesheet_record_color" && data) {
            if (data.timesheet_record_color === "Red") {
                return `<span style="background-color:#ff4d4d; color:white; padding:2px 6px; border-radius:4px;">${value}</span>`;
            }
            if (data.timesheet_record_color === "Green") {
                return `<span style="background-color:#28a745; color:white; padding:2px 6px; border-radius:4px;">${value}</span>`;
            }
            if (data.timesheet_record_color === "Amber") {
                return `<span style="background-color:#ffc107; color:black; padding:2px 6px; border-radius:4px;">${value}</span>`;
            }
        }

        return value;
    }
};
