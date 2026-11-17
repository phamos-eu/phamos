/** Edge glow of a cockpit window (#1933): pure helpers, used by composables/useCockpitGlow.js. */

/** How long the glow stays bright after the window comes to the front (ms). */
export const PULSE_MS = 1500

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

/**
 * What the glow does for a cockpit_window boot value ({color, glow}).
 *
 * @returns {{rgb: string, steady: boolean, pulse: boolean} | null} null when there is no glow
 */
export function glowSettings(cockpitWindow) {
	const rgb = hexToRgbTriplet(cockpitWindow?.color)
	const mode = MODES[cockpitWindow?.glow]
	return rgb && mode ? { rgb, ...mode } : null
}
