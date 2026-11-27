// The Ophice map's camera and image placement (#2089): pure maths, no DOM, so it can be tested.
// Map units are grid tiles; screen units are px. The walkable grid always spans (0,0)-(cols,rows).

export const ZOOM_MIN = 1
export const ZOOM_MAX = 3
// Past the edge the map follows the hand with resistance, at most this far (px).
export const RUBBER_MAX = 80
export const RUBBER_FACTOR = 0.35

/** Half-tile steps, as the spaces use (#2067). */
export function snapHalf(value) {
	return Math.round(value * 2) / 2
}

export function clampZoom(zoom) {
	return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, Number(zoom) || 1))
}

/** The largest whole-px tile that fits the whole grid into a box, with a padding around it. */
export function fitTile(width, height, cols, rows, pad = 16, min = 4) {
	if (!width || !height || !cols || !rows) return 0
	return Math.max(min, Math.floor(Math.min((width - 2 * pad) / cols, (height - 2 * pad) / rows)))
}

/** An image of this ratio covering the grid, centred: { left, top, width, height } in tiles. */
export function coverPlacement(ratio, cols, rows) {
	const r = ratio > 0 ? ratio : cols / rows
	if (r >= cols / rows) {
		const height = rows
		const width = height * r
		return { left: (cols - width) / 2, top: 0, width, height }
	}
	const width = cols
	const height = width / r
	return { left: 0, top: (rows - height) / 2, width, height }
}

/** Where the background lies, in tiles: covering the grid ("fit"), or as placed in edit mode. */
export function imagePlacement(layout, ratio, cols, rows) {
	if (!layout || layout.fit) return coverPlacement(ratio, cols, rows)
	const r = ratio > 0 ? ratio : cols / rows
	const width = Number(layout.width) || cols
	return { left: Number(layout.left) || 0, top: Number(layout.top) || 0, width, height: width / r }
}

/** The whole map: the grid and the image together (the image may reach beyond the grid). */
export function canvasRect(cols, rows, image) {
	if (!image) return { x: 0, y: 0, w: cols, h: rows }
	const x = Math.min(0, image.left)
	const y = Math.min(0, image.top)
	const right = Math.max(cols, image.left + image.width)
	const bottom = Math.max(rows, image.top + image.height)
	return { x, y, w: right - x, h: bottom - y }
}

/** The pan range on one axis: content smaller than the view stays centred. */
export function panBounds(view, content, pad = 16) {
	if (content + 2 * pad <= view) {
		const centre = (view - content) / 2
		return { min: centre, max: centre }
	}
	return { min: view - content - pad, max: pad }
}

export function clamp(value, bounds) {
	return Math.max(bounds.min, Math.min(bounds.max, value))
}

/** How far the map shows past the edge for `over` px of hand movement beyond it: the bounce. */
export function rubber(over, max = RUBBER_MAX, factor = RUBBER_FACTOR) {
	if (!over) return 0
	return Math.sign(over) * Math.min(max, Math.abs(over) * factor)
}

/** The pan that keeps the map point under `point` (px in the view) still while the tile changes. */
export function zoomAround(pan, oldTile, newTile, point) {
	const world = (point - pan) / oldTile
	return point - world * newTile
}

/**
 * The pan that keeps `target` (px in the view) at least `margin` px inside the view, moving as
 * little as possible: the camera follows my chip.
 */
export function follow(pan, target, view, margin) {
	if (target < margin) return pan + (margin - target)
	if (target > view - margin) return pan - (target - (view - margin))
	return pan
}
