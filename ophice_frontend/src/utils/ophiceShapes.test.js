import { describe, expect, it } from "vitest"
import { boxCorners, boxOf, clipPath, contains, labelPoint, nearestInside, selfCrossing, shapeOf } from "./ophiceShapes.js"

// An L: 0..4 x 0..4 without its top right quarter 2..4 x 0..2.
const L = {
	x: 0,
	y: 0,
	width: 4,
	height: 4,
	shape: "Polygon",
	points: [
		[0, 0],
		[2, 0],
		[2, 2],
		[4, 2],
		[4, 4],
		[0, 4],
	],
}

describe("area shapes (#2144)", () => {
	it("tests inside by shape, as the server does", () => {
		expect(contains(L, 1, 3)).toBe(true)
		expect(contains(L, 3, 1)).toBe(false)
		expect(contains(L, 3, 1.6, 0.5)).toBe(true)
		const ellipse = { x: 0, y: 0, width: 4, height: 2, shape: "Ellipse" }
		expect(contains(ellipse, 2, 1)).toBe(true)
		expect(contains(ellipse, 0.2, 0.2)).toBe(false)
		expect(contains({ x: 0, y: 0, width: 2, height: 2 }, 2, 1)).toBe(false) // a box is half open
	})

	it("falls back to the box for a polygon without corners", () => {
		expect(shapeOf({ shape: "Polygon", points: [] })).toBe("Rectangle")
	})

	it("puts the label inside an L-shaped polygon", () => {
		const [x, y] = labelPoint(L)
		expect(contains(L, x, y)).toBe(true)
	})

	it("keeps a point inside the shape", () => {
		const [x, y] = nearestInside(L, 3.5, 0.5)
		expect(contains(L, x, y)).toBe(true)
	})

	it("finds crossing edges", () => {
		expect(
			selfCrossing([
				[0, 0],
				[4, 4],
				[4, 0],
				[0, 4],
			])
		).toBe(true)
		expect(selfCrossing(L.points)).toBe(false)
	})

	it("turns a box into corners and back", () => {
		const box = { x: 1, y: 2, width: 3, height: 4 }
		expect(boxOf(boxCorners(box))).toEqual(box)
	})

	it("cuts ellipses and polygons for the guest view", () => {
		expect(clipPath({ x: 0, y: 0, width: 4, height: 2, shape: "Ellipse" }, 10)).toBe("ellipse(20px 10px at 20px 10px)")
		expect(clipPath(L, 10)).toMatch(/^polygon\(0px 0px, 20px 0px/)
		expect(clipPath({ x: 0, y: 0, width: 1, height: 1 }, 10)).toBeNull()
	})
})
