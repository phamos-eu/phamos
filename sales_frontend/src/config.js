import { LEAD_LAYOUT, LEAD_PANELS } from "./panels/leadPanels.js"

export default {
	api: "phamos.api.sales_spa",
	label: "Sales",
	slug: "sales",
	basePath: "/sales-cockpit",
	departmentField: "sales_department",
	settingsMethod: "get_sales_settings",
	projectField: "sales_standard_project",
	projectNameField: "sales_standard_project_name",
	barColorStyleId: "sales-gantt-bar-colors",
	// The Lead page as tiles (#1913): its panels and default layout belong to this cockpit.
	panels: { Lead: { add: LEAD_PANELS } },
	panelLayouts: { Lead: LEAD_LAYOUT },
}
