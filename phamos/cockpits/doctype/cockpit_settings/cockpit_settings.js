// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

// "Open Cockpit" at the top of each tab opens that cockpit in a new browser tab, so a change
// can be checked right away (#1932). Keys are the Button fields (<prefix>_open_cockpit).
const COCKPIT_ROUTES = {
	human_resources_open_cockpit: "/human-resources-cockpit",
	personal_open_cockpit: "/personal-cockpit",
	project_management_open_cockpit: "/project-management-cockpit",
	sales_open_cockpit: "/sales-cockpit",
	accounting_open_cockpit: "/accounting-cockpit",
	software_development_open_cockpit: "/software-development-cockpit",
	general_management_open_cockpit: "/general-management-cockpit",
};

frappe.ui.form.on(
	"Cockpit Settings",
	Object.fromEntries(
		Object.entries(COCKPIT_ROUTES).map(([field, route]) => [
			field,
			() => window.open(route, "_blank", "noopener"),
		])
	)
);
