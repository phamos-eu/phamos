import { describe, expect, it } from "vitest"
import { CORNER_BOTTOM, CORNER_RIGHT, cornerBox, dropZone, isOverCorner } from "./miniMapCorner.js"

// The mini map docked over the bottom-right corner (#2155), left of Phriend.
const viewport = { w: 1280, h: 800 }

describe("cornerBox", () => {
	it("sits left of Phriend, at the bottom, growing upwards", () => {
		const box = cornerBox(viewport)
		expect(box.left + box.width).toBe(viewport.w - CORNER_RIGHT)
		expect(box.bottom).toBe(CORNER_BOTTOM)
		expect(box.height).toBeNull()
		expect(box.maxHeight).toBe(480)
	})

	it("gets a fixed height in a meeting, never taller than the window", () => {
		expect(cornerBox(viewport, { meeting: true }).height).toBe(560)
		expect(cornerBox({ w: 1280, h: 400 }, { meeting: true }).height).toBe(368)
	})

	it("stays on screen in a narrow window", () => {
		const box = cornerBox({ w: 320, h: 600 })
		expect(box.left).toBeGreaterThanOrEqual(8)
		expect(box.width).toBeGreaterThanOrEqual(200)
	})
})

describe("isOverCorner", () => {
	it("docks when let go in the drop zone, also over Phriend's corner", () => {
		const zone = dropZone(viewport)
		expect(isOverCorner(zone.left + 10, zone.top + 10, viewport)).toBe(true)
		expect(isOverCorner(1260, 790, viewport)).toBe(true)
	})

	it("hovers when let go elsewhere", () => {
		expect(isOverCorner(500, 700, viewport)).toBe(false)
		expect(isOverCorner(1100, 200, viewport)).toBe(false)
	})
})
