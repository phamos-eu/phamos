import { describe, expect, it } from "vitest"
import { glowSettings, hexToRgbTriplet } from "./cockpitGlow.js"

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
		const color = "#c2410c"
		expect(glowSettings({ color, glow: "Always" })).toEqual({ rgb: "194 65 12", steady: true, pulse: false })
		expect(glowSettings({ color, glow: "On focus" })).toEqual({ rgb: "194 65 12", steady: false, pulse: true })
		expect(glowSettings({ color, glow: "Always + on focus" })).toEqual({
			rgb: "194 65 12",
			steady: true,
			pulse: true,
		})
	})

	it("has no glow when it is off, unknown or without a colour", () => {
		expect(glowSettings({ color: "#c2410c", glow: "Off" })).toBeNull()
		expect(glowSettings({ color: "#c2410c", glow: "Sometimes" })).toBeNull()
		expect(glowSettings({ color: null, glow: "Always" })).toBeNull()
		expect(glowSettings(undefined)).toBeNull()
	})
})
