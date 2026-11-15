import {
	GUTTER,
	clone,
	distribute,
	evenAt,
	fit,
	insertNear,
	layout,
	leaves,
	minSize,
	normalize,
	resizeAt,
	resolve,
	sanitize,
	touched,
	withAll,
} from "./tiling.js"

// Today's Issue page: description | chat over phriend over checklists | properties
const issueTree = () => ({
	split: "row",
	sizes: [0.4, 0.4, 0.2],
	children: [
		{ panel: "description" },
		{ split: "column", sizes: [0.6, 0.2, 0.2], children: [{ panel: "chat" }, { panel: "phriend" }, { panel: "checklists" }] },
		{ panel: "properties" },
	],
})
const ALL = new Set(["description", "chat", "phriend", "checklists", "properties"])
const mins = { chat: { w: 768, h: 320 } }
const sum = (list) => list.reduce((a, b) => a + b, 0)
const close = (a, b) => Math.abs(a - b) < 0.001

describe("sanitize", () => {
	it("drops bad nodes and duplicates, collapses one-child splits, normalises", () => {
		const dirty = {
			split: "row",
			sizes: [2, "x", -1],
			children: [{ panel: "a" }, { split: "diagonal", children: [] }, { split: "column", children: [{ panel: "a" }, { panel: "b" }] }],
		}
		// the column kept only "b" (its "a" is a duplicate); a bad size counts as an equal share
		expect(sanitize(dirty)).toEqual({ split: "row", sizes: [0.8, 0.2], children: [{ panel: "a" }, { panel: "b" }] })
		expect(sanitize({ panel: "" })).toBeNull()
		expect(sanitize("nope")).toBeNull()
	})

	it("refuses trees deeper than six levels", () => {
		let deep = { panel: "x" }
		for (let i = 0; i < 8; i++) deep = { split: "row", sizes: [1, 1], children: [deep, { panel: `p${i}` }] }
		expect(leaves(sanitize(deep))).not.toContain("x")
	})
})

describe("resolve", () => {
	it("leaves closed panels out and gives their space to the siblings", () => {
		const shown = new Set(["description", "chat", "properties"])
		const r = resolve(issueTree(), shown)
		expect(leaves(r)).toEqual(["description", "chat", "properties"])
		// the column kept only the chat: it is replaced by the chat itself
		expect(r.children[1]).toEqual({ panel: "chat" })
		expect(close(sum(r.sizes), 1)).toBe(true)
	})

	it("returns null when nothing shows", () => {
		expect(resolve(issueTree(), new Set())).toBeNull()
	})
})

describe("minSize", () => {
	it("adds up along a split and takes the largest across it", () => {
		const m = minSize(resolve(issueTree(), ALL), mins)
		expect(m.w).toBe(240 + 768 + 240 + 2 * GUTTER)
		expect(m.h).toBe(320 + 120 + 120 + 2 * GUTTER)
	})
})

describe("distribute", () => {
	it("keeps proportions when every panel fits", () => {
		expect(distribute([0.25, 0.75], [10, 10], 100)).toEqual([25, 75])
	})
	it("raises a panel to its minimum and shares the rest", () => {
		const px = distribute([0.2, 0.4, 0.4], [768, 100, 100], 1200)
		expect(px[0]).toBe(768)
		expect(close(px[1], 216)).toBe(true)
		expect(close(sum(px), 1200)).toBe(true)
	})
})

describe("layout", () => {
	it("fills the whole rect without gaps", () => {
		const { tiles, gutters } = layout(resolve(issueTree(), ALL), { x: 0, y: 0, w: 1600, h: 900 }, mins)
		const row = tiles.filter((t) => t.y === 0)
		const right = Math.max(...tiles.map((t) => t.x + t.w))
		expect(close(right, 1600)).toBe(true)
		expect(tiles.find((t) => t.id === "chat").w).toBeGreaterThanOrEqual(768)
		const column = tiles.filter((t) => ["chat", "phriend", "checklists"].includes(t.id))
		expect(close(sum(column.map((t) => t.h)) + 2 * GUTTER, 900)).toBe(true)
		expect(row.map((t) => t.id)).toEqual(["description", "chat", "properties"])
		expect(gutters.length).toBe(4)
	})
})

describe("resizeAt", () => {
	it("moves only the two neighbours and keeps their minimums", () => {
		const tree = issueTree()
		const r = resolve(tree, ALL)
		const avail = 2400 - 2 * GUTTER // wide enough that the chat column is above its minimum
		const before = distribute(r.sizes, [240, 768, 240], avail)
		resizeAt(r, 0, 100, avail, mins) // description wider, the column narrower
		const after = distribute(normalize(tree.sizes), [240, 768, 240], avail)
		expect(close(after[0], before[0] + 100)).toBe(true)
		expect(close(after[2], before[2])).toBe(true)
		// a huge drag stops at the chat's 768
		const r2 = resolve(tree, ALL)
		resizeAt(r2, 0, 5000, avail, mins)
		const px = distribute(normalize(tree.sizes), [240, 768, 240], avail)
		expect(close(px[1], 768)).toBe(true)
	})

	it("keeps the share of a closed sibling for when it comes back", () => {
		const tree = issueTree()
		const shown = new Set(["description", "chat", "properties"])
		const r = resolve(tree, shown)
		resizeAt(r, 0, -50, 1592, mins)
		expect(close(sum(tree.sizes), 1)).toBe(true)
		expect(tree.children[1].sizes).toEqual([0.6, 0.2, 0.2]) // the column inside is untouched
	})

	it("evens a splitter", () => {
		const tree = issueTree()
		evenAt(resolve(tree, ALL), 0)
		expect(close(tree.sizes[0], tree.sizes[1])).toBe(true)
	})
})

describe("fit", () => {
	const opened = ["phriend", "checklists", "properties", "chat", "description"]

	it("closes nothing when everything fits", () => {
		expect(fit(issueTree(), ALL, opened, mins, { w: 1600, h: 900 }).size).toBe(0)
	})

	it("closes the panel opened longest ago that makes room", () => {
		// too narrow: phriend and checklists sit under the chat and don't help; properties do
		expect([...fit(issueTree(), ALL, opened, mins, { w: 1100, h: 900 })]).toEqual(["properties"])
	})

	it("closes for height too, and never the panel opened last", () => {
		const hidden = fit(issueTree(), ALL, opened, mins, { w: 1600, h: 450 })
		expect([...hidden]).toEqual(["phriend"])
		const tiny = fit(issueTree(), ALL, opened, mins, { w: 100, h: 100 })
		expect(tiny.has("description")).toBe(false)
	})

	it("brings panels back when the window grows (fit is computed from scratch)", () => {
		expect(fit(issueTree(), ALL, opened, mins, { w: 1100, h: 900 }).size).toBe(1)
		expect(fit(issueTree(), ALL, opened, mins, { w: 1600, h: 900 }).size).toBe(0)
	})
})

describe("insertNear and withAll", () => {
	it("splits the target in half on the asked side", () => {
		const tree = { split: "row", sizes: [0.5, 0.5], children: [{ panel: "a" }, { panel: "b" }] }
		const right = insertNear(tree, "n", "a", "right")
		expect(leaves(right)).toEqual(["a", "n", "b"])
		expect(right.sizes).toEqual([0.25, 0.25, 0.5])
		const top = insertNear(tree, "n", "b", "top")
		expect(top.children[1]).toEqual({ split: "column", sizes: [0.5, 0.5], children: [{ panel: "n" }, { panel: "b" }] })
		expect(leaves(tree)).toEqual(["a", "b"]) // the original is untouched
	})

	it("adds to the right of everything without a target", () => {
		expect(leaves(insertNear({ panel: "a" }, "n", "missing"))).toEqual(["a", "n"])
		expect(insertNear(null, "n")).toEqual({ panel: "n" })
	})

	it("places panels the tree doesn't know yet", () => {
		const tree = withAll(issueTree(), ["description", "notes"], { notes: { near: "checklists", side: "bottom" } })
		expect(leaves(tree)).toEqual(["description", "chat", "phriend", "checklists", "notes", "properties"])
	})
})

describe("touched", () => {
	it("moves a panel to the end of the opening order", () => {
		expect(touched(["a", "b", "c"], "a")).toEqual(["b", "c", "a"])
		expect(touched(undefined, "a")).toEqual(["a"])
	})
})

describe("clone", () => {
	it("copies deeply", () => {
		const tree = issueTree()
		const copy = clone(tree)
		copy.children[1].sizes[0] = 1
		expect(tree.children[1].sizes[0]).toBe(0.6)
	})
})
