// The "Team" field on the Issue and Task pages (#1955).
//
// The server sends the teams the user may put a record into (`options.teams`) in every cockpit
// except the Team Cockpit, where a record's team is the cockpit's own. A record of another team
// keeps that team as a choice, so the field shows its value instead of an empty select.

/**
 * Whether the page shows the field: only when the user may put records into a team. A user in no
 * team does not see a record's team either; the field is a tool for members, not information.
 */
export function showTeamField(options) {
	return Array.isArray(options?.teams) && options.teams.length > 0
}

/** Select options: "—" for no team, the user's teams, and the record's own team if it is another. */
export function teamOptions(options, current) {
	const teams = Array.isArray(options?.teams) ? [...options.teams] : []
	if (current && !teams.includes(current)) teams.push(current)
	return [{ label: "—", value: "" }, ...teams.map((team) => ({ label: team, value: team }))]
}

/** A record of another team can't be moved by this user; the server refuses it as well. */
export function teamFieldLocked(options, current) {
	return Boolean(current) && !(options?.teams || []).includes(current)
}
