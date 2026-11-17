/** Edge glow of a cockpit window (#1933): pure helpers, used by composables/useCockpitGlow.js. */

/** Length of the focus glow (ms): the cockpit-glow-focus animation in spa_shared/main.css. */
export const PULSE_MS = 1600

/** Window edges the glow can come from, as the boot lists them. */
export const GLOW_EDGES = ["top", "left", "bottom", "right"]

// Glow modes as stored in Cockpit Settings (<prefix>_glow); "Off" and anything unknown: no glow.
const MODES = {
	Always: { steady: true, pulse: false },
	"On focus": { steady: false, pulse: true },
	"Always + on focus": { steady: true, pulse: true },
}

/** "#c2410c" → "194 65 12", for rgb(var(--cockpit-rgb) / 30%) in CSS; null for anything else. */
export function hexToRgbTriplet(hex) {
	const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "")
	return match ? match.slice(1).map((part) => parseInt(part, 16)).join(" ") : null
}

// Corners drawn round where both of their edges glow, so the two strips don't meet in a square.
export const CORNERS = [
	["top-left", "top", "left"],
	["top-right", "top", "right"],
	["bottom-left", "bottom", "left"],
	["bottom-right", "bottom", "right"],
]

/**
 * What the glow does for a cockpit_window boot value ({color, glow, edges, breathing}).
 *
 * @returns {{rgb: string, steady: boolean, pulse: boolean, breathing: boolean, edges: string[],
 *   corners: string[]} | null} null when there is no glow: no colour, mode off or unknown, or no
 *   edge switched on
 */
export function glowSettings(cockpitWindow) {
	const rgb = hexToRgbTriplet(cockpitWindow?.color)
	const mode = MODES[cockpitWindow?.glow]
	const edges = GLOW_EDGES.filter((edge) => (cockpitWindow?.edges || []).includes(edge))
	if (!rgb || !mode || !edges.length) return null
	const corners = CORNERS.filter(([, a, b]) => edges.includes(a) && edges.includes(b)).map(([name]) => name)
	return { rgb, ...mode, breathing: !!cockpitWindow.breathing, edges, corners }
}

/** CSS variables for the glow layer: the colour and 1/0 per edge (--glow-top, ...). */
export function glowStyle(settings) {
	const style = { "--cockpit-rgb": settings.rgb }
	for (const edge of GLOW_EDGES) style[`--glow-${edge}`] = settings.edges.includes(edge) ? 1 : 0
	return style
}
