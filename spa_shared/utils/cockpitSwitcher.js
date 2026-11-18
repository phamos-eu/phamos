/**
 * The menu behind the cockpit name in the sidebar (#1955): the user's other cockpits.
 *
 * Pure, so it can be tested without a browser; CockpitSidebar.vue turns the entries into a menu.
 */

/** True when `path` is the cockpit at `route` or a page inside it. */
export function isCurrentCockpit(route, path) {
	return path === route || path.startsWith(`${route}/`)
}

/**
 * The cockpits to switch to, in the order the server sent them (the Apps screen's order). The
 * open cockpit is left out: its name is already the menu's label.
 *
 * @param {Array<{route: string, title: string}>} cockpits from the boot (phamos/www/spa_boot.py)
 * @param {string} path the page's location.pathname
 * @returns {Array<{route: string, title: string}>}
 */
export function otherCockpits(cockpits, path) {
	return (cockpits || [])
		.filter((cockpit) => cockpit && cockpit.route && !isCurrentCockpit(cockpit.route, path || ""))
		.map((cockpit) => ({ route: cockpit.route, title: cockpit.title || cockpit.route }))
}
