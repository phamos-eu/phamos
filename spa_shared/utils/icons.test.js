import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"
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

	it("gives the Ideas entry of every cockpit's menu the light bulb", () => {
		// a cockpit that picks its own Feather icon for ideas (the Team Cockpit's "zap") breaks the one symbol
		const root = join(__dirname, "..", "..")
		const apps = readdirSync(root).filter((d) => d.endsWith("_frontend"))
		const entries = apps.flatMap((app) => {
			let source = ""
			try {
				source = readFileSync(join(root, app, "src", "App.vue"), "utf8")
			} catch {
				return []
			}
			return [...source.matchAll(/label: "Ideas",\s*icon: ([^,]+),/g)].map((m) => `${app}: ${m[1]}`)
		})
		expect(entries.length).toBeGreaterThan(1)
		for (const entry of entries) expect(entry).toMatch(/IDEA_ICON$/)
	})
})
