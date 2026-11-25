// Shapes of meeting areas (#2144): rectangle, ellipse, polygon. The same rules as
// phamos/api/ophice_shapes.py, so the map and the server agree on who is inside.
//
// Every area keeps x, y, width, height (tiles) as its box; an ellipse fills its box, a polygon
// has corner points ([[x, y], ...], half tiles) and its box comes from them.

export const SHAPES = ["Rectangle", "Ellipse", "Polygon"]
export const MAX_POINTS = 40

export function shapeOf(area) {
	if (area?.shape === "Polygon") return pointsOf(area).length >= 3 ? "Polygon" : "Rectangle"
	return area?.shape === "Ellipse" ? "Ellipse" : "Rectangle"
}

export function pointsOf(area) {
	const raw = area?.points
	return Array.isArray(raw) ? raw.filter((p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1])) : []
}

/** Even-odd ray casting. */
export function inPolygon(points, px, py) {
	let inside = false
	for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
		const [x1, y1] = points[i]
		const [x2, y2] = points[j]
		if (y1 > py !== y2 > py && px < x1 + ((py - y1) * (x2 - x1)) / (y2 - y1)) inside = !inside
	}
	return inside
}

function nearestOnSegment([ax, ay], [bx, by], px, py) {
	const dx = bx - ax
	const dy = by - ay
	const length = dx * dx + dy * dy
	const t = length ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / length)) : 0
	return [ax + t * dx, ay + t * dy]
}

/** The distance from a point to the segment a-b. */
export function segmentDistance(a, b, px, py) {
	const [qx, qy] = nearestOnSegment(a, b, px, py)
	return Math.hypot(px - qx, py - qy)
}

/** [distance, [x, y]] of the nearest point on the polygon's edges. */
export function edgeDistance(points, px, py) {
	let best = [Infinity, [px, py]]
	for (let i = 0; i < points.length; i++) {
		const q = nearestOnSegment(points[i], points[(i + 1) % points.length], px, py)
		const d = Math.hypot(px - q[0], py - q[1])
		if (d < best[0]) best = [d, q]
	}
	return best
}

/** True when the point (tiles) lies in the area, or within `slack` of its edge. */
export function contains(area, px, py, slack = 0) {
	const { x, y, width: w, height: h } = area
	const shape = shapeOf(area)
	if (shape === "Rectangle") return px >= x - slack && px < x + w + slack && py >= y - slack && py < y + h + slack
	if (px < x - slack || px > x + w + slack || py < y - slack || py > y + h + slack) return false
	if (shape === "Ellipse") {
		const rx = w / 2 + slack
		const ry = h / 2 + slack
		return rx > 0 && ry > 0 && ((px - x - w / 2) / rx) ** 2 + ((py - y - h / 2) / ry) ** 2 <= 1
	}
	const points = pointsOf(area)
	if (inPolygon(points, px, py)) return true
	return slack > 0 && edgeDistance(points, px, py)[0] <= slack
}

/** The point of the area nearest to (px, py), itself when inside (guests are kept in). */
export function nearestInside(area, px, py) {
	if (contains(area, px, py)) return [px, py]
	const { x, y, width: w, height: h } = area
	const shape = shapeOf(area)
	if (shape === "Ellipse" && w > 0 && h > 0) {
		const cx = x + w / 2
		const cy = y + h / 2
		const dx = px - cx
		const dy = py - cy
		const scale = Math.hypot(dx / (w / 2), dy / (h / 2))
		return scale ? [cx + (dx / scale) * 0.999, cy + (dy / scale) * 0.999] : [cx, cy]
	}
	if (shape === "Polygon") {
		const points = pointsOf(area)
		const [qx, qy] = edgeDistance(points, px, py)[1]
		// A hair off the edge, to whichever side is inside.
		for (let angle = 0; angle < 360; angle += 45) {
			const nx = qx + 0.01 * Math.cos((angle * Math.PI) / 180)
			const ny = qy + 0.01 * Math.sin((angle * Math.PI) / 180)
			if (inPolygon(points, nx, ny)) return [nx, ny]
		}
		return [qx, qy]
	}
	return [Math.min(Math.max(px, x), x + w - 1e-6), Math.min(Math.max(py, y), y + h - 1e-6)]
}

/**
 * Where the name and logo go, in tiles: the middle of the box, or for a polygon whose middle lies
 * outside (an L shape) the half-tile spot inside it nearest to that middle.
 */
export function labelPoint(area) {
	const cx = area.x + area.width / 2
	const cy = area.y + area.height / 2
	if (shapeOf(area) !== "Polygon") return [cx, cy]
	const points = pointsOf(area)
	// Well inside (away from the edges) and near the middle; the middle itself when that is fine.
	const score = (x, y) => Math.min(edgeDistance(points, x, y)[0], 1.5) - 0.3 * Math.hypot(x - cx, y - cy)
	if (inPolygon(points, cx, cy) && edgeDistance(points, cx, cy)[0] >= 1) return [cx, cy]
	let best = null
	for (let y = area.y + 0.25; y < area.y + area.height; y += 0.5) {
		for (let x = area.x + 0.25; x < area.x + area.width; x += 0.5) {
			if (!inPolygon(points, x, y)) continue
			const s = score(x, y)
			if (!best || s > best[0]) best = [s, x, y]
		}
	}
	return best ? [best[1], best[2]] : [cx, cy]
}

/** The box of a list of points: { x, y, width, height }. */
export function boxOf(points) {
	const xs = points.map((p) => p[0])
	const ys = points.map((p) => p[1])
	const x = Math.min(...xs)
	const y = Math.min(...ys)
	return { x, y, width: Math.max(...xs) - x, height: Math.max(...ys) - y }
}

/** The four corners of a box, clockwise from the top left: a rectangle turned into a polygon. */
export function boxCorners({ x, y, width, height }) {
	return [
		[x, y],
		[x + width, y],
		[x + width, y + height],
		[x, y + height],
	]
}

/** The polygon's points relative to its box, for an SVG with viewBox "0 0 width height". */
export function svgPoints(area) {
	return pointsOf(area)
		.map(([px, py]) => `${px - area.x},${py - area.y}`)
		.join(" ")
}

/** A CSS clip-path of the area's shape, in px inside an element whose (0, 0) is tile (0, 0). */
export function clipPath(area, tile) {
	const shape = shapeOf(area)
	if (shape === "Ellipse") {
		return `ellipse(${(area.width / 2) * tile}px ${(area.height / 2) * tile}px at ${(area.x + area.width / 2) * tile}px ${(area.y + area.height / 2) * tile}px)`
	}
	if (shape === "Polygon") return `polygon(${pointsOf(area).map(([px, py]) => `${px * tile}px ${py * tile}px`).join(", ")})`
	return null
}

function cross(o, a, b) {
	return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
}

/** True when two edges of the polygon cross (the server refuses such a polygon). */
export function selfCrossing(points) {
	const n = points.length
	for (let i = 0; i < n; i++) {
		for (let j = i + 1; j < n; j++) {
			if (j === i + 1 || (i === 0 && j === n - 1)) continue
			const p1 = points[i]
			const p2 = points[(i + 1) % n]
			const q1 = points[j]
			const q2 = points[(j + 1) % n]
			const d1 = cross(q1, q2, p1)
			const d2 = cross(q1, q2, p2)
			const d3 = cross(p1, p2, q1)
			const d4 = cross(p1, p2, q2)
			if (d1 && d2 && d3 && d4 && d1 > 0 !== d2 > 0 && d3 > 0 !== d4 > 0) return true
		}
	}
	return false
}
