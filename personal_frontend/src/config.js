// Personal Cockpit: scoped to the session user, not to a department, so there is no
// departmentField / projectField; spa_shared treats their absence as "no department".
export default {
	api: "phamos.api.personal_cockpit",
	label: "Personal Cockpit",
	slug: "personal",
	basePath: "/personal-cockpit",
	personal: true,
	settingsMethod: "get_personal_settings",
	barColorStyleId: "personal-gantt-bar-colors",
}
