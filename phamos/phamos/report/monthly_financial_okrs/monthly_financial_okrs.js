// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.query_reports["Monthly Financial OKRs"] = {
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