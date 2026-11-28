// The shared cockpit code Ophice reuses reads its API module from here (`@/config`).
// Only the timesheet timer uses it so far (#2101): the Personal Cockpit's timer, so Ophice and the
// Personal Cockpit start, pause and stop the same timer. Ophice's own calls stay on phamos.api.ophice.
export default {
	api: "phamos.api.personal_cockpit",
	label: "Ophice",
	slug: "ophice",
	personal: true,
}
