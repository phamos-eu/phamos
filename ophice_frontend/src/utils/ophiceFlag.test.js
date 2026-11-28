import { describe, expect, it } from "vitest"
import { FLAG_COLORS, FLAG_PATTERNS, cellAt, flagBlocked, flagHue } from "./ophiceFlag.js"

describe("cellAt", () => {
	it("floors a point to its cell", () => {
		expect(cellAt(3.9, 0.1, 10, 10)).toEqual({ x: 3, y: 0 })
	})
	it("is null off the grid", () => {
		expect(cellAt(-0.1, 2, 10, 10)).toBeNull()
		expect(cellAt(10, 2, 10, 10)).toBeNull()
		expect(cellAt(NaN, 2, 10, 10)).toBeNull()
	})
})

describe("flagBlocked", () => {
	const areas = [{ x: 2, y: 2, width: 3, height: 2 }]
	const flags = [{ user: "b@x", x: 7, y: 7 }]

	it("allows a free cell", () => {
		expect(flagBlocked({ x: 0, y: 0 }, { areas, flags, user: "a@x" })).toBe("")
	})
	it("blocks a cell inside an area, edges by the cell's middle", () => {
		expect(flagBlocked({ x: 2, y: 2 }, { areas, flags, user: "a@x" })).toBe("area")
		expect(flagBlocked({ x: 4, y: 3 }, { areas, flags, user: "a@x" })).toBe("area")
		expect(flagBlocked({ x: 5, y: 3 }, { areas, flags, user: "a@x" })).toBe("")
	})
	it("blocks another person's flag, not my own", () => {
		expect(flagBlocked({ x: 7, y: 7 }, { areas, flags, user: "a@x" })).toBe("flag")
		expect(flagBlocked({ x: 7, y: 7 }, { areas, flags, user: "b@x" })).toBe("")
	})
	it("blocks no cell", () => {
		expect(flagBlocked(null)).toBe("off")
	})
})

describe("colours and patterns", () => {
	it("match the server's lists", () => {
		expect(Object.keys(FLAG_COLORS)).toEqual(["red", "orange", "amber", "green", "teal", "blue", "violet", "pink"])
		expect(FLAG_PATTERNS).toEqual(["plain", "dots", "stripes", "grid", "waves"])
	})
	it("falls back to red for an unknown colour", () => {
		expect(flagHue("nope")).toBe(FLAG_COLORS.red)
	})
})
