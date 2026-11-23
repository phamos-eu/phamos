import { describe, expect, it } from "vitest"
import {
	canvasRect,
	clamp,
	coverPlacement,
	fitTile,
	follow,
	imagePlacement,
	isCutOff,
	panBounds,
	rubber,
	snapHalf,
	zoomAround,
} from "./ophiceView.js"

describe("Ophice map camera (#2089)", () => {
	it("fits the whole grid into the view", () => {
		expect(fitTile(1032, 532, 40, 25)).toBe(20)
		expect(fitTile(0, 500, 40, 25)).toBe(0)
	})

	it("covers the grid with a wide or tall image, centred", () => {
		expect(coverPlacement(2, 40, 25)).toEqual({ left: -5, top: 0, width: 50, height: 25 })
		expect(coverPlacement(1, 40, 25)).toEqual({ left: 0, top: -7.5, width: 40, height: 40 })
		expect(imagePlacement({ fit: false, left: 2, top: -1, width: 30 }, 1.5, 40, 25)).toEqual({ left: 2, top: -1, width: 30, height: 20 })
	})

	it("makes the map the grid and the image together", () => {
		expect(canvasRect(40, 25, null)).toEqual({ x: 0, y: 0, w: 40, h: 25 })
		expect(canvasRect(40, 25, { left: -5, top: 2, width: 60, height: 30 })).toEqual({ x: -5, y: 0, w: 60, h: 32 })
	})

	it("centres a small map and keeps a big one inside its edges", () => {
		expect(panBounds(1000, 600)).toEqual({ min: 200, max: 200 })
		expect(panBounds(1000, 1600)).toEqual({ min: -616, max: 16 })
		expect(clamp(50, { min: -616, max: 16 })).toBe(16)
	})

	it("bounces past the edge with resistance, up to a cap", () => {
		expect(rubber(0)).toBe(0)
		expect(rubber(100)).toBeCloseTo(35)
		expect(rubber(-1000)).toBe(-80)
	})

	it("keeps the point under the cursor still while zooming", () => {
		const pan = zoomAround(100, 20, 40, 300)
		// The map point under x=300 was (300-100)/20 = 10 tiles; it is still under x=300.
		expect((300 - pan) / 40).toBe(10)
	})

	it("follows the chip only when it gets close to the edge", () => {
		expect(follow(0, 500, 1000, 200)).toBe(0)
		expect(follow(0, 900, 1000, 200)).toBe(-100)
		expect(follow(0, 50, 1000, 200)).toBe(150)
	})

	it("snaps to half tiles", () => {
		expect(snapHalf(3.26)).toBe(3.5)
		expect(snapHalf(3.2)).toBe(3)
	})
})

describe("isCutOff (#2096)", () => {
	it("is true only when the text is wider than the label", () => {
		expect(isCutOff({ scrollWidth: 140, clientWidth: 80 })).toBe(true)
		expect(isCutOff({ scrollWidth: 80, clientWidth: 80 })).toBe(false)
		expect(isCutOff({ scrollWidth: 81, clientWidth: 80 })).toBe(false) // sub-pixel rounding
		expect(isCutOff(null)).toBe(false)
	})
})
