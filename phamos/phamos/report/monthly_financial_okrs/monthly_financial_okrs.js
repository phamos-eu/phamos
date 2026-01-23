// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.query_reports["Monthly Financial OKRs"] = {
        formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (!data) return value;

        // Quarter totals
        if (data.month && data.month.includes("Total")) {
            value = `<div style="
                font-weight:bold;
            ">${value}</div>`;
        }

        // Grand total
        if (data.month && data.month.includes("Grand Total")) {
            value = `<div style="
                font-weight:bold;
            ">${value}</div>`;
        }

        return value;
    },
    "filters": [
        {
            fieldname: "year",
            label: __("Year"),
            fieldtype: "Select",
            options: get_last_five_years(),
            default: frappe.datetime.get_today().split("-")[0]
        }
    ]
};

function get_last_five_years() {
    const currentYear = new Date().getFullYear();
    let options = "";
    for (let i = 0; i < 5; i++) {
        options += (currentYear - i) + "\n";
    }
    return options.trim();
}