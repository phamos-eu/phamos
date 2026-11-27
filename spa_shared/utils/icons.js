// Icons the cockpits draw themselves where Feather has none (#2207). Same style as Feather:
// 24px grid, 2px stroke, round ends, current text colour. CockpitIcon.vue renders them and
// falls back to Feather for every other name.

export const CUSTOM_ICON_PATHS = {
	// light bulb: the Idea Catcher's symbol (spa_shared/scripts/symbols/lightbulb.svg, #2202), so
	// ideas look the same on the phone and in the cockpits
	lightbulb: [
		"M9 18h6",
		"M10 21.5h4",
		"M12 2.5a6.5 6.5 0 0 0-3.9 11.7c.8.6 1.4 1.5 1.4 2.3h5c0-.8.6-1.7 1.4-2.3A6.5 6.5 0 0 0 12 2.5z",
	],
}

// The Idea doctype's icon, wherever a cockpit shows ideas.
export const IDEA_ICON = "lightbulb"

export function isCustomIcon(name) {
	return typeof name === "string" && Object.hasOwn(CUSTOM_ICON_PATHS, name)
}
