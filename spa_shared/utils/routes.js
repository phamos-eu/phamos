// Route list for a cockpit router (#1604, #1612): the shared routes plus the cockpit's own,
// where a cockpit route with the name of a shared one replaces it (e.g. the Personal Cockpit's
// own Issues and Tasks start pages). Pure, so it can be tested without a browser.
export function withOwnRoutes(shared, own = []) {
	const names = new Set(own.map((route) => route.name).filter(Boolean))
	return [...shared.filter((route) => !names.has(route.name)), ...own]
}
