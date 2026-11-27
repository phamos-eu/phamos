import { describe, expect, it } from "vitest"
import { CUSTOM_ICON_PATHS, IDEA_ICON, isCustomIcon } from "./icons.js"

describe("cockpit icons (#2207)", () => {
	it("draws ideas as a light bulb, not Feather's feather", () => {
		expect(IDEA_ICON).toBe("lightbulb")
		expect(isCustomIcon(IDEA_ICON)).toBe(true)
		expect(CUSTOM_ICON_PATHS[IDEA_ICON].length).toBeGreaterThan(0)
	})

	it("leaves Feather names to Feather", () => {
		expect(isCustomIcon("feather")).toBe(false)
		expect(isCustomIcon("list")).toBe(false)
		expect(isCustomIcon(undefined)).toBe(false)
		expect(isCustomIcon("constructor")).toBe(false)
	})
})
