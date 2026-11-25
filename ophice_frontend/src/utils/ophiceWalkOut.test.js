import { describe, expect, it } from "vitest"
import { areaUnder, walkedOut } from "./ophiceWalkOut.js"

// Over a cockpit (#2155): leaving the area I stood in goes back to the map.
const areas = [
	{ name: "sales", kind: "Cockpit", x: 10, y: 10, width: 6, height: 4 },
	{ name: "talk", kind: "Meeting", x: 30, y: 5, width: 5, height: 5 },
]

describe("areaUnder", () => {
	it("finds the area of any kind under the chip's middle", () => {
		expect(areaUnder(areas, { x: 12, y: 11 })?.name).toBe("sales")
		expect(areaUnder(areas, { x: 31, y: 6 })?.name).toBe("talk")
	})

	it("counts the right and bottom edge as outside", () => {
		// Middle at 16.5: past the right edge at 16.
		expect(areaUnder(areas, { x: 16, y: 11 })).toBeNull()
		expect(areaUnder(areas, { x: 15, y: 11 })?.name).toBe("sales")
	})

	it("is null without a chip or areas", () => {
		expect(areaUnder(areas, null)).toBeNull()
		expect(areaUnder(null, { x: 12, y: 11 })).toBeNull()
	})
})

describe("walkedOut", () => {
	it("is false while the chip stays in the area", () => {
		expect(walkedOut("sales", areas, { x: 14, y: 12 })).toBe(false)
	})

	it("is true once the chip is out, also straight into another area", () => {
		expect(walkedOut("sales", areas, { x: 20, y: 12 })).toBe(true)
		expect(walkedOut("sales", areas, { x: 31, y: 6 })).toBe(true)
	})

	it("never sends back when the cockpit was opened outside any area", () => {
		expect(walkedOut(null, areas, { x: 20, y: 12 })).toBe(false)
	})
})
