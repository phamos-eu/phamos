import { describe, expect, it } from "vitest"
import { glowSettings, glowStyle, hexToRgbTriplet } from "./cockpitGlow.js"

const color = "#c2410c"
const edges = ["bottom", "right"]

describe("cockpit edge glow (#1933)", () => {
	it("turns a hex colour into the CSS rgb triplet", () => {
		expect(hexToRgbTriplet("#c2410c")).toBe("194 65 12")
		expect(hexToRgbTriplet("#0E7490")).toBe("14 116 144")
	})

	it("refuses anything that is not #rrggbb", () => {
		for (const value of [null, undefined, "", "c2410c", "#c24", "#c2410cff", "red", "#gg0000"]) {
			expect(hexToRgbTriplet(value)).toBeNull()
		}
	})

	it("maps each glow mode to steady and pulse", () => {
		const base = { rgb: "194 65 12", edges, corners: ["bottom-right"], breathing: false }
		expect(glowSettings({ color, glow: "Always", edges })).toEqual({ ...base, steady: true, pulse: false })
		expect(glowSettings({ color, glow: "On focus", edges })).toEqual({ ...base, steady: false, pulse: true })
		expect(glowSettings({ color, glow: "Always + on focus", edges })).toEqual({ ...base, steady: true, pulse: true })
		expect(glowSettings({ color, glow: "Always", edges, breathing: true }).breathing).toBe(true)
	})

	it("keeps only known edges, in a fixed order", () => {
		expect(glowSettings({ color, glow: "Always", edges: ["right", "middle", "top"] }).edges).toEqual(["top", "right"])
	})

	it("rounds only the corners where both edges glow", () => {
		const corners = (list) => glowSettings({ color, glow: "Always", edges: list }).corners
		expect(corners(["bottom"])).toEqual([])
		expect(corners(["top", "bottom"])).toEqual([])
		expect(corners(["left", "bottom", "right"])).toEqual(["bottom-left", "bottom-right"])
		expect(corners(["top", "left", "bottom", "right"])).toEqual(["top-left", "top-right", "bottom-left", "bottom-right"])
	})

	it("has no glow when it is off, unknown, without a colour or without an edge", () => {
		expect(glowSettings({ color, glow: "Off", edges })).toBeNull()
		expect(glowSettings({ color, glow: "Sometimes", edges })).toBeNull()
		expect(glowSettings({ color: null, glow: "Always", edges })).toBeNull()
		expect(glowSettings({ color, glow: "Always", edges: [] })).toBeNull()
		expect(glowSettings({ color, glow: "Always" })).toBeNull()
		expect(glowSettings(undefined)).toBeNull()
	})

	it("switches each edge on or off in the style", () => {
		expect(glowStyle(glowSettings({ color, glow: "Always", edges }))).toEqual({
			"--cockpit-rgb": "194 65 12",
			"--glow-top": 0,
			"--glow-left": 0,
			"--glow-bottom": 1,
			"--glow-right": 1,
		})
	})
})
