// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.query_reports["Timesheet Summary"] = {
    "filters": [
        {
            "fieldname": "range_type",
            "label": __("Range Type"),
            "fieldtype": "Select",
            "options": ["Timespan", "Between"],
            "default": "Timespan",
            "reqd": 1,
            "on_change": function() {
                frappe.query_report.refresh();
            }
        },
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
            "depends_on": "eval:doc.range_type == 'Timespan'",
            "reqd": 1
        },
        {
            "fieldname": "start_date",
            "label": __("Start Date"),
            "fieldtype": "Date",
            "depends_on": "eval:doc.range_type == 'Between'",
            "reqd": 1
        },
        {
            "fieldname": "end_date",
            "label": __("End Date"),
            "fieldtype": "Date",
            "depends_on": "eval:doc.range_type == 'Between'",
            "reqd": 1
        }
    ]
};