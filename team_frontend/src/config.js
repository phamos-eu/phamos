// No departmentField or projectField: the cockpit follows the user's active team, which the
// server resolves (phamos.cockpits.teams), not a Department from Cockpit Settings.
export default {
	api: "phamos.api.team_cockpit",
	label: "Team",
	slug: "team",
	basePath: "/team-cockpit",
	settingsMethod: "get_team_settings",
	barColorStyleId: "team-gantt-bar-colors",
}
