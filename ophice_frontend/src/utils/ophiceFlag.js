// My flag (#2129, #2130): one flag per person, planted on a cell of the map. The cloth has the
// person's colour and pattern. Not inside an area, not on a cell that already has a flag.

/** The same keys as FLAG_COLORS in phamos/api/ophice.py; the value is the hue. */
export const FLAG_COLORS = {
	red: 2,
	orange: 24,
	amber: 42,
	green: 130,
	teal: 172,
	blue: 212,
	violet: 268,
	pink: 328,
}
/** The same keys as FLAG_PATTERNS in phamos/api/ophice.py. */
export const FLAG_PATTERNS = ["plain", "dots", "stripes", "grid", "waves"]

export function flagHue(color) {
	return FLAG_COLORS[color] ?? FLAG_COLORS.red
}

/** The cell under a point of the map, in tiles (fractions allowed), or null off the grid. */
export function cellAt(x, y, cols, rows) {
	const cx = Math.floor(x)
	const cy = Math.floor(y)
	if (!Number.isFinite(cx) || !Number.isFinite(cy) || cx < 0 || cy < 0 || cx >= cols || cy >= rows) return null
	return { x: cx, y: cy }
}

/**
 * Why `user`'s flag can't stand on `cell`: "area", "flag", or "" when it can. The server checks
 * the same (set_my_flag); this is for the preview while aiming.
 */
export function flagBlocked(cell, { areas = [], flags = [], user = "" } = {}) {
	if (!cell) return "off"
	const cx = cell.x + 0.5
	const cy = cell.y + 0.5
	if (areas.some((a) => cx >= a.x && cx < a.x + a.width && cy >= a.y && cy < a.y + a.height)) return "area"
	if (flags.some((f) => f.user !== user && f.x === cell.x && f.y === cell.y)) return "flag"
	return ""
}
