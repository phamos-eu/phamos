// Icons the cockpits draw themselves where Feather has none (#2207). Same style as Feather:
// 24px grid, 2px stroke, round ends, current text colour. CockpitIcon.vue renders them and
// falls back to Feather for every other name.

export const CUSTOM_ICON_PATHS = {
	// light bulb, after Lucide's "lightbulb" (ISC licence, a Feather fork)
	lightbulb: [
		"M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5",
		"M9 18h6",
		"M10 22h4",
	],
}

// The Idea doctype's icon, wherever a cockpit shows ideas.
export const IDEA_ICON = "lightbulb"

export function isCustomIcon(name) {
	return typeof name === "string" && Object.hasOwn(CUSTOM_ICON_PATHS, name)
}
