// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.query_reports["Timesheet Summary"] = {
    "filters": [
        {
            "fieldname": "time_period",
            "label": __("Time Period"),
            "fieldtype": "Select",
            "options": [
                "Last Week",
                "Last 2 Weeks",
                "Last Month",
                "Last 3 Months",
                "Last 6 Months"
            ],
            "default": "Last Month",
            "on_change": function() {
                // Automatically refreshes the report when the selection changes
                frappe.query_report.refresh();
            }
        }
    ]
};