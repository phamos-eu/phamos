// The tiling layout of a record page (#1915): a tree of splits whose leaves are panels.
//
//   node = { panel: "<id>" }
//        | { split: "row" | "column", sizes: [fractions], children: [node, ...] }
//
// The stored tree keeps every panel the user placed, open or not; the page shows `resolve(tree,
// shown)`, in which closed, hidden and missing panels are left out and their siblings take the
// space. So a closed panel comes back where it was, and the fractions of the others stay as the
// user set them.
//
// Pure functions only (the vitest setup runs in node without Vue).

/** Space between two tiles, in px; also the splitter's hit area. */
export const GUTTER = 4
/** A panel's size when its declaration names none. */
export const DEFAULT_MIN = { w: 240, h: 120 }
const MAX_DEPTH = 6

const isSplit = (node) => Boolean(node && Array.isArray(node.children))
const axisOf = (node) => (node.split === "row" ? "w" : "h")

/** Panel ids in the tree, in reading order. */
export function leaves(node) {
	if (!node) return []
	if (!isSplit(node)) return [node.panel]
	return node.children.flatMap(leaves)
}

/** Fractions that add up to 1; non-positive or missing entries count as an equal share. */
export function normalize(sizes, count = sizes.length) {
	const list = Array.from({ length: count }, (_, i) => {
		const n = Number(sizes?.[i])
		return Number.isFinite(n) && n > 0 ? n : 0
	})
	const fallback = 1 / count
	const filled = list.map((n) => n || fallback)
	const sum = filled.reduce((a, b) => a + b, 0)
	return filled.map((n) => n / sum)
}

/**
 * A stored tree, checked: unknown shapes are dropped, duplicate panels keep their first place,
 * fractions are normalised. Returns null when nothing is left.
 */
export function sanitize(node, seen = new Set(), depth = 0) {
	if (!node || typeof node !== "object" || depth > MAX_DEPTH) return null
	if (typeof node.panel === "string") {
		if (!node.panel || seen.has(node.panel)) return null
		seen.add(node.panel)
		return { panel: node.panel }
	}
	if ((node.split !== "row" && node.split !== "column") || !Array.isArray(node.children)) return null
	const kept = []
	node.children.forEach((child, i) => {
		const clean = sanitize(child, seen, depth + 1)
		if (clean) kept.push({ node: clean, size: node.sizes?.[i] })
	})
	if (!kept.length) return null
	if (kept.length === 1) return kept[0].node
	return {
		split: node.split,
		sizes: normalize(kept.map((k) => k.size)),
		children: kept.map((k) => k.node),
	}
}

/** A deep copy, so a change can be made and saved without touching the reactive original. */
export function clone(node) {
	return node ? JSON.parse(JSON.stringify(node)) : null
}

/**
 * The tree as shown: only the panels in `shown` (a Set). A split left with one child is replaced
 * by it. Each shown split remembers its stored node (`src`) and which stored children it shows
 * (`srcIdx`), so a resize can be written back.
 */
export function resolve(node, shown) {
	if (!node) return null
	if (!isSplit(node)) return shown.has(node.panel) ? { panel: node.panel } : null
	const kept = []
	node.children.forEach((child, i) => {
		const r = resolve(child, shown)
		if (r) kept.push({ r, i })
	})
	if (!kept.length) return null
	if (kept.length === 1) return kept[0].r
	return {
		split: node.split,
		sizes: normalize(kept.map((k) => node.sizes[k.i])),
		children: kept.map((k) => k.r),
		src: node,
		srcIdx: kept.map((k) => k.i),
	}
}

/** The smallest size a (resolved) node can take: { w, h }. `mins` maps a panel id to { w, h }. */
export function minSize(node, mins = {}) {
	if (!node) return { w: 0, h: 0 }
	if (!isSplit(node)) return { ...DEFAULT_MIN, ...(mins[node.panel] || {}) }
	const parts = node.children.map((c) => minSize(c, mins))
	const gutters = GUTTER * (parts.length - 1)
	if (node.split === "row") {
		return { w: parts.reduce((s, p) => s + p.w, 0) + gutters, h: Math.max(...parts.map((p) => p.h)) }
	}
	return { w: Math.max(...parts.map((p) => p.w)), h: parts.reduce((s, p) => s + p.h, 0) + gutters }
}

/**
 * Pixel sizes for fractions within `avail`, each at least its minimum where possible: panels
 * below their minimum get it, the others share the rest in their proportions. Adds up to `avail`
 * (unless even the minimums don't fit, which `fit` prevents).
 */
export function distribute(fractions, minima, avail) {
	const n = fractions.length
	const px = fractions.map((f) => f * avail)
	const fixed = new Array(n).fill(false)
	for (let round = 0; round < n; round++) {
		const below = px.map((p, i) => !fixed[i] && p < minima[i] - 0.01)
		if (!below.some(Boolean)) break
		below.forEach((b, i) => {
			if (b) {
				fixed[i] = true
				px[i] = minima[i]
			}
		})
		const used = px.reduce((s, p, i) => s + (fixed[i] ? p : 0), 0)
		const rest = Math.max(0, avail - used)
		const share = fractions.reduce((s, f, i) => s + (fixed[i] ? 0 : f), 0)
		px.forEach((_, i) => {
			if (!fixed[i]) px[i] = share ? (fractions[i] / share) * rest : 0
		})
	}
	return px
}

/**
 * Where everything goes in a rect { x, y, w, h }: `tiles` [{ id, x, y, w, h }] and `gutters`
 * [{ x, y, w, h, axis, path, index, avail }]: the splitter between child `index` and the next of
 * the split at `path` (child indices from the root; see `splitAt`).
 */
export function layout(node, rect, mins = {}) {
	const out = { tiles: [], gutters: [] }
	place(node, rect, mins, out, [])
	return out
}

/** The node at `path` (child indices) in a tree. */
export function splitAt(node, path) {
	return path.reduce((n, i) => n?.children?.[i], node)
}

function place(node, rect, mins, out, path) {
	if (!node) return
	if (!isSplit(node)) {
		out.tiles.push({ id: node.panel, ...rect })
		return
	}
	const axis = axisOf(node)
	const n = node.children.length
	const avail = Math.max(0, (axis === "w" ? rect.w : rect.h) - GUTTER * (n - 1))
	const minima = node.children.map((c) => minSize(c, mins)[axis])
	const px = distribute(node.sizes, minima, avail)
	let offset = axis === "w" ? rect.x : rect.y
	node.children.forEach((child, i) => {
		const size = px[i]
		const childRect = axis === "w" ? { x: offset, y: rect.y, w: size, h: rect.h } : { x: rect.x, y: offset, w: rect.w, h: size }
		place(child, childRect, mins, out, [...path, i])
		offset += size
		if (i < n - 1) {
			out.gutters.push(
				axis === "w"
					? { x: offset, y: rect.y, w: GUTTER, h: rect.h, axis, path, index: i, avail }
					: { x: rect.x, y: offset, w: rect.w, h: GUTTER, axis, path, index: i, avail }
			)
			offset += GUTTER
		}
	})
}

/**
 * Move the splitter after child `index` of a resolved split by `delta` px. Only those two
 * children change; each keeps its minimum. Writes the new fractions into the stored split
 * (`node.src`), keeping the share of the children not shown.
 */
export function resizeAt(node, index, delta, avail, mins = {}) {
	const axis = axisOf(node)
	const minima = node.children.map((c) => minSize(c, mins)[axis])
	const px = distribute(node.sizes, minima, avail)
	const pair = px[index] + px[index + 1]
	const a = Math.min(Math.max(px[index] + delta, minima[index]), pair - minima[index + 1])
	if (a < minima[index]) return false // the two don't even fit at their minimum
	px[index] = a
	px[index + 1] = pair - a
	const stored = node.src.sizes
	const shownShare = node.srcIdx.reduce((s, i) => s + stored[i], 0)
	const total = px.reduce((s, p) => s + p, 0) || 1
	node.srcIdx.forEach((si, k) => (stored[si] = (px[k] / total) * shownShare))
	return true
}

/** Make the splitter after child `index` even: both children get the same share. */
export function evenAt(node, index) {
	const stored = node.src.sizes
	const [a, b] = [node.srcIdx[index], node.srcIdx[index + 1]]
	const half = (stored[a] + stored[b]) / 2
	stored[a] = half
	stored[b] = half
}

/**
 * Which shown panels must close because the window is too small (#1915): the one opened longest
 * ago first, but only one whose closing actually helps (a panel stacked under the chat doesn't
 * make the row narrower). The panel opened last always stays.
 *
 * @param {object} tree the stored tree
 * @param {Set<string>} shown panels that would show
 * @param {string[]} opened panel ids, oldest opening first
 * @param {object} mins id → { w, h }
 * @param {{ w: number, h: number }} room
 * @returns {Set<string>} the panels to leave out for now
 */
export function fit(tree, shown, opened, mins, room) {
	const left = new Set(shown)
	const hidden = new Set()
	const order = [...[...shown].filter((id) => !opened.includes(id)), ...opened.filter((id) => shown.has(id))]
	const keep = order[order.length - 1]
	for (let guard = 0; guard < order.length; guard++) {
		const need = minSize(resolve(tree, left), mins)
		const tooWide = need.w > room.w
		const tooHigh = need.h > room.h
		if (!tooWide && !tooHigh) break
		const helps = order.find((id) => {
			if (!left.has(id) || id === keep) return false
			const without = new Set(left)
			without.delete(id)
			const after = minSize(resolve(tree, without), mins)
			return (tooWide && after.w < need.w) || (tooHigh && after.h < need.h)
		})
		if (!helps) break
		left.delete(helps)
		hidden.add(helps)
	}
	return hidden
}

/**
 * The tree with panel `id` placed on `side` ("left" | "right" | "top" | "bottom") of panel
 * `target`, halving the target's space. Without the target, it goes to the right of everything.
 */
export function insertNear(tree, id, target, side = "right") {
	const leaf = { panel: id }
	if (!tree) return leaf
	const axis = side === "left" || side === "right" ? "row" : "column"
	const before = side === "left" || side === "top"
	const root = clone(tree)
	const path = findPath(root, target)
	if (!path) {
		if (isSplit(root) && root.split === "row") {
			const share = 1 / (root.children.length + 1)
			root.sizes = [...root.sizes.map((s) => s * (1 - share)), share]
			root.children.push(leaf)
			return root
		}
		return { split: "row", sizes: [0.75, 0.25], children: [root, leaf] }
	}
	if (!path.length) {
		return { split: axis, sizes: [0.5, 0.5], children: before ? [leaf, root] : [root, leaf] }
	}
	const parent = nodeAt(root, path.slice(0, -1))
	const i = path[path.length - 1]
	if (parent.split === axis) {
		const half = parent.sizes[i] / 2
		parent.sizes.splice(i, 1, half, half)
		parent.children.splice(before ? i : i + 1, 0, leaf)
		return root
	}
	parent.children[i] = {
		split: axis,
		sizes: [0.5, 0.5],
		children: before ? [leaf, parent.children[i]] : [parent.children[i], leaf],
	}
	return root
}

function findPath(node, id, path = []) {
	if (!isSplit(node)) return node.panel === id ? path : null
	for (let i = 0; i < node.children.length; i++) {
		const found = findPath(node.children[i], id, [...path, i])
		if (found) return found
	}
	return null
}

function nodeAt(node, path) {
	return path.reduce((n, i) => n.children[i], node)
}

/**
 * The stored tree with every panel in `ids` placed: ones the tree doesn't know yet (a panel
 * added in a later release, or by a cockpit) go where their declaration says ({ near, side }),
 * else to the right of everything.
 */
export function withAll(tree, ids, places = {}) {
	let next = tree
	const known = new Set(leaves(tree))
	for (const id of ids) {
		if (known.has(id)) continue
		const place = places[id] || {}
		next = insertNear(next, id, place.near, place.side)
		known.add(id)
	}
	return next
}

/** `opened` with `id` moved to the end: it was opened last. */
export function touched(opened, id) {
	return [...(opened || []).filter((x) => x !== id), id]
}

/** The tree without panel `id`; a split left with one child is replaced by it. */
export function remove(tree, id) {
	if (!tree) return null
	if (!isSplit(tree)) return tree.panel === id ? null : tree
	const kept = []
	tree.children.forEach((child, i) => {
		const next = remove(child, id)
		if (next) kept.push({ node: next, size: tree.sizes[i] })
	})
	if (!kept.length) return null
	if (kept.length === 1) return kept[0].node
	return { split: tree.split, sizes: normalize(kept.map((k) => k.size)), children: kept.map((k) => k.node) }
}

/** The share a panel gets when it is put on an edge of the whole page. */
export const PAGE_EDGE_SHARE = 0.3

/**
 * The tree with panel `id` moved (#1916): to `side` of panel `target`, halving it, or with
 * `target` null to `side` of the whole page: full width at the top or bottom, full height on the
 * left or right. Moving a panel onto itself changes nothing.
 */
export function move(tree, id, target, side) {
	if (target === id) return tree
	const rest = remove(clone(tree), id)
	if (!rest) return { panel: id }
	if (target) return insertNear(rest, id, target, side)
	const axis = side === "left" || side === "right" ? "row" : "column"
	const before = side === "left" || side === "top"
	const leaf = { panel: id }
	if (isSplit(rest) && rest.split === axis) {
		const sizes = rest.sizes.map((s) => s * (1 - PAGE_EDGE_SHARE))
		return {
			split: axis,
			sizes: before ? [PAGE_EDGE_SHARE, ...sizes] : [...sizes, PAGE_EDGE_SHARE],
			children: before ? [leaf, ...rest.children] : [...rest.children, leaf],
		}
	}
	return {
		split: axis,
		sizes: before ? [PAGE_EDGE_SHARE, 1 - PAGE_EDGE_SHARE] : [1 - PAGE_EDGE_SHARE, PAGE_EDGE_SHARE],
		children: before ? [leaf, rest] : [rest, leaf],
	}
}

/** The tree with panels `a` and `b` in each other's place; sizes stay with the places. */
export function swap(tree, a, b) {
	if (a === b) return tree
	const walk = (node) => {
		if (!isSplit(node)) return { panel: node.panel === a ? b : node.panel === b ? a : node.panel }
		return { split: node.split, sizes: [...node.sizes], children: node.children.map(walk) }
	}
	return tree ? walk(tree) : tree
}

/**
 * Where a drop at (x, y) lands, for the drag of a panel's title bar (#1916): within `edge` px of
 * the page's border → { target: null, side } (whole page); inside a tile → its centre third swaps
 * ({ target, side: "center" }), elsewhere the nearest edge splits it. `tiles` and the point are in
 * the page's coordinates; `size` is the page's { w, h }.
 */
export function dropAt(x, y, tiles, size, edge = 24) {
	if (x < 0 || y < 0 || x > size.w || y > size.h) return null
	const page = [
		["left", x],
		["right", size.w - x],
		["top", y],
		["bottom", size.h - y],
	].sort((p, q) => p[1] - q[1])[0]
	if (page[1] <= edge) return { target: null, side: page[0] }
	const tile = tiles.find((t) => x >= t.x && x <= t.x + t.w && y >= t.y && y <= t.y + t.h)
	if (!tile) return null
	const fx = (x - tile.x) / tile.w
	const fy = (y - tile.y) / tile.h
	if (fx > 1 / 3 && fx < 2 / 3 && fy > 1 / 3 && fy < 2 / 3) return { target: tile.id, side: "center" }
	const sides = [
		["left", fx],
		["right", 1 - fx],
		["top", fy],
		["bottom", 1 - fy],
	].sort((p, q) => p[1] - q[1])
	return { target: tile.id, side: sides[0][0] }
}

/** The tree after a drop from `dropAt`. */
export function dropped(tree, id, drop) {
	if (!drop) return tree
	if (drop.side === "center") return swap(tree, id, drop.target)
	return move(tree, id, drop.target, drop.side)
}

/**
 * The stored opening order, or the default when there is none: an empty list counts as none (a
 * layout saved by an older version, or cleaned on the server, has `opened: []`).
 */
export function openingOrder(stored, fallback = []) {
	return Array.isArray(stored) && stored.length ? stored : fallback
}
