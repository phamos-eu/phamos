import { describe, expect, it } from "vitest"
import { History, bounds, hit, moved, shape_at } from "./shapes.js"

const text = (x, y, extra = {}) => ({ type: "text", x, y, text: "Hi", size: 10, width: 20, w: 4, ...extra })
const box = (x1, y1, x2, y2) => ({ type: "box", x1, y1, x2, y2, w: 4 })
const redact = (x1, y1, x2, y2) => ({ type: "redact", x1, y1, x2, y2, w: 4 })
const arrow = (a, b) => ({ type: "pen", points: [a, b], w: 4 })
const free = (...points) => ({ type: "free", points, w: 4 })

describe("bounds", () => {
	it("includes the padding of a text label", () => {
		// pad = 3, height = 12
		expect(bounds(text(100, 50))).toEqual({ x1: 97, y1: 47, x2: 123, y2: 65 })
	})

	it("orders the corners of a box drawn up and to the left", () => {
		expect(bounds(box(40, 30, 10, 5))).toEqual({ x1: 10, y1: 5, x2: 40, y2: 30 })
	})
})

describe("hit", () => {
	it("grabs a text label and a black-out bar anywhere on them", () => {
		expect(hit(text(100, 50), { x: 110, y: 55 }, 0)).toBe(true)
		expect(hit(redact(0, 0, 100, 40), { x: 50, y: 20 }, 0)).toBe(true)
	})

	it("misses a text label outside it, plus the tolerance", () => {
		expect(hit(text(100, 50), { x: 130, y: 55 }, 2)).toBe(false)
		expect(hit(text(100, 50), { x: 124, y: 55 }, 2)).toBe(true)
	})

	it("grabs a box on its edge, not in its middle", () => {
		const b = box(0, 0, 200, 100)
		expect(hit(b, { x: 100, y: 1 }, 3)).toBe(true)
		expect(hit(b, { x: 203, y: 50 }, 3)).toBe(true)
		expect(hit(b, { x: 100, y: 50 }, 3)).toBe(false)
	})

	it("grabs an arrow near its line, not beyond its ends", () => {
		const a = arrow({ x: 0, y: 0 }, { x: 100, y: 0 })
		expect(hit(a, { x: 50, y: 4 }, 3)).toBe(true) // 3 + half of w 4
		expect(hit(a, { x: 50, y: 6 }, 3)).toBe(false)
		expect(hit(a, { x: 110, y: 0 }, 3)).toBe(false)
	})

	it("grabs a free line near any of its segments, not across its bend", () => {
		const f = free({ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 100 })
		expect(hit(f, { x: 101, y: 60 }, 2)).toBe(true)
		expect(hit(f, { x: 50, y: 50 }, 2)).toBe(false)
	})
})

describe("shape_at", () => {
	it("takes the topmost (newest) shape where shapes overlap", () => {
		const shapes = [text(0, 0), text(5, 0)]
		expect(shape_at(shapes, { x: 10, y: 5 }, 0)).toBe(1)
	})

	it("is -1 on empty screenshot", () => {
		expect(shape_at([box(0, 0, 200, 100)], { x: 100, y: 50 }, 3)).toBe(-1)
	})
})

describe("moved", () => {
	it("shifts every kind of shape and leaves the original alone", () => {
		const t = text(10, 10)
		expect(moved(t, 5, -2)).toMatchObject({ x: 15, y: 8, text: "Hi" })
		expect(t.x).toBe(10)
		expect(moved(box(0, 0, 10, 10), 1, 2)).toMatchObject({ x1: 1, y1: 2, x2: 11, y2: 12 })
		expect(moved(redact(0, 0, 10, 10), 1, 2)).toMatchObject({ type: "redact", x1: 1, y2: 12 })
		expect(moved(arrow({ x: 0, y: 0 }, { x: 4, y: 4 }), 1, 1).points).toEqual([
			{ x: 1, y: 1 },
			{ x: 5, y: 5 },
		])
		expect(moved(free({ x: 0, y: 0 }, { x: 1, y: 1 }, { x: 2, y: 0 }), 0, 3).points[2]).toEqual({ x: 2, y: 3 })
	})
})

describe("History", () => {
	it("undoes an added shape", () => {
		const shapes = []
		const h = new History(shapes)
		h.add(text(0, 0))
		expect(h.undo()).toBe(true)
		expect(shapes).toEqual([])
		expect(h.undo()).toBe(false)
	})

	it("deletes one shape and undo puts it back at its place", () => {
		const a = text(0, 0)
		const b = text(50, 0)
		const c = text(100, 0)
		const shapes = [a, b, c]
		const h = new History(shapes)
		h.remove(1)
		expect(shapes).toEqual([a, c])
		h.undo()
		expect(shapes).toEqual([a, b, c])
	})

	it("undoes a drag that already moved the shape live", () => {
		const before = text(0, 0)
		const shapes = [before]
		const h = new History(shapes)
		const after = moved(before, 30, 40)
		shapes[0] = after // as the pointer drags it
		h.replace(0, after, { before })
		h.undo()
		expect(shapes[0]).toBe(before)
	})

	it("undoes a text edit", () => {
		const before = text(0, 0)
		const shapes = [before]
		const h = new History(shapes)
		h.replace(0, { ...before, text: "Changed" })
		expect(shapes[0].text).toBe("Changed")
		h.undo()
		expect(shapes[0].text).toBe("Hi")
	})

	it("undoes actions newest first: add, move, delete", () => {
		const shapes = []
		const h = new History(shapes)
		const t = text(0, 0)
		h.add(t)
		h.add(box(0, 0, 10, 10))
		h.replace(0, moved(t, 5, 5))
		h.remove(1)
		h.undo() // the box is back
		expect(shapes).toHaveLength(2)
		h.undo() // the text is back where it was
		expect(shapes[0]).toBe(t)
		h.undo()
		h.undo()
		expect(shapes).toEqual([])
	})

	it("joins a run of nudges into one step, until it is sealed", () => {
		const t = text(0, 0)
		const shapes = [t]
		const h = new History(shapes)
		h.replace(0, moved(shapes[0], 1, 0), { merge: "nudge" })
		h.replace(0, moved(shapes[0], 1, 0), { merge: "nudge" })
		h.seal()
		h.replace(0, moved(shapes[0], 1, 0), { merge: "nudge" })
		expect(shapes[0].x).toBe(3)
		h.undo()
		expect(shapes[0].x).toBe(2)
		h.undo()
		expect(shapes[0]).toBe(t)
	})

	it("doesn't join nudges of different shapes", () => {
		const shapes = [text(0, 0), text(50, 0)]
		const h = new History(shapes)
		h.replace(0, moved(shapes[0], 1, 0), { merge: "nudge" })
		h.replace(1, moved(shapes[1], 1, 0), { merge: "nudge" })
		h.undo()
		expect(shapes[1].x).toBe(50)
		expect(shapes[0].x).toBe(1)
	})
})
