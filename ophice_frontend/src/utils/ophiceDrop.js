import { contains } from "./ophiceShapes.js"

// Leaving a meeting by choice (Leave, Esc): the chip is lifted out of the meeting space and set
// down just outside it, so the others no longer see it standing in the meeting.

/** How far outside the border the chip's centre lands, in tiles. */
export const DROP_MARGIN = 0.8
/** How much further out it may go when the first spot is taken, in tiles. */
const DROP_REACH = 3
const DROP_STEP = 0.5

// By shape (#2144); the borders below are the box's, so a spot outside the box is outside any shape.
function inside(area, cx, cy) {
	return contains(area, cx, cy)
}

/**
 * The spot just outside `area` nearest to `chip` (positions are a chip's top left corner, the
 * chip is one tile). Straight across the nearest border first, then further out, then the other
 * borders. Never off the map, on another chip (`isFree`) or in another meeting space.
 * Returns { x, y } or null when there is no room anywhere.
 */
export function dropSpotOutside(area, chip, { cols, rows, isFree = () => true, otherAreas = [] }) {
	const cx = chip.x + 0.5
	const cy = chip.y + 0.5
	const right = area.x + area.width
	const bottom = area.y + area.height
	const borders = [
		{ distance: cx - area.x, spot: (k) => [area.x - k, cy] },
		{ distance: right - cx, spot: (k) => [right + k, cy] },
		{ distance: cy - area.y, spot: (k) => [cx, area.y - k] },
		{ distance: bottom - cy, spot: (k) => [cx, bottom + k] },
	].sort((a, b) => a.distance - b.distance)
	for (const border of borders) {
		for (let k = DROP_MARGIN; k <= DROP_MARGIN + DROP_REACH; k += DROP_STEP) {
			const [centreX, centreY] = border.spot(k)
			const x = centreX - 0.5
			const y = centreY - 0.5
			// Off the map: further out only gets further off.
			if (x < 0 || y < 0 || x > cols - 1 || y > rows - 1) break
			if (inside(area, centreX, centreY) || otherAreas.some((a) => inside(a, centreX, centreY))) continue
			if (!isFree(x, y)) continue
			return { x: Math.round(x * 100) / 100, y: Math.round(y * 100) / 100 }
		}
	}
	return null
}
