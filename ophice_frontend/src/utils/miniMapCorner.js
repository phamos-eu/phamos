// The mini map's docked place over a cockpit (#2155): a box floating over the bottom-right corner
// of the window, left of Phriend (the cockpit's report ball sits 24 px from the corner, 64 px wide).
// Dragged out it hovers; dropped back near the corner it docks again.

export const CORNER_RIGHT = 100
export const CORNER_BOTTOM = 16
export const CORNER_WIDTH = 300
/** The drop zone's height: let go in it and the map docks. */
export const DROP_HEIGHT = 220
// A meeting (call and chat) needs room; without one the box fits the map and the pings.
const MEETING_HEIGHT = 560
const MAX_HEIGHT = 480

/** The docked box in a window of `viewport` ({ w, h }), as fixed-position style values (px). */
export function cornerBox(viewport, { meeting = false } = {}) {
	const room = Math.max(160, viewport.h - CORNER_BOTTOM - 16)
	const width = Math.min(CORNER_WIDTH, Math.max(200, viewport.w - CORNER_RIGHT - 16))
	return {
		left: Math.max(8, viewport.w - CORNER_RIGHT - width),
		bottom: CORNER_BOTTOM,
		width,
		// Meeting: a fixed height; otherwise at most this tall, growing upwards with the pings.
		height: meeting ? Math.min(MEETING_HEIGHT, room) : null,
		maxHeight: Math.min(MAX_HEIGHT, room),
	}
}

/** Where the drop zone shows while the map is dragged, in the window (px). */
export function dropZone(viewport) {
	const box = cornerBox(viewport)
	return { left: box.left, top: viewport.h - CORNER_BOTTOM - DROP_HEIGHT, width: box.width, height: DROP_HEIGHT }
}

/** Let go here and the dragged map docks: in the drop zone, with a little slack. */
export function isOverCorner(x, y, viewport, slack = 24) {
	const zone = dropZone(viewport)
	return x >= zone.left - slack && x <= viewport.w && y >= zone.top - slack && y <= viewport.h
}
