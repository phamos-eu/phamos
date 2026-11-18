import { describe, expect, it } from "vitest"
import { isCurrentCockpit, otherCockpits } from "./cockpitSwitcher.js"

const PERSONAL = { route: "/personal-cockpit", title: "Personal Cockpit" }
const TEAM = { route: "/team-cockpit", title: "Team Cockpit" }
const SALES = { route: "/sales-cockpit", title: "Sales" }

describe("isCurrentCockpit", () => {
	it("matches the cockpit and the pages inside it", () => {
		expect(isCurrentCockpit("/team-cockpit", "/team-cockpit")).toBe(true)
		expect(isCurrentCockpit("/team-cockpit", "/team-cockpit/tasks/gantt")).toBe(true)
	})

	it("does not match a cockpit whose route only starts the same", () => {
		expect(isCurrentCockpit("/team", "/team-cockpit")).toBe(false)
		expect(isCurrentCockpit("/team-cockpit", "/personal-cockpit")).toBe(false)
	})
})

describe("otherCockpits", () => {
	it("keeps the server's order and leaves the open cockpit out", () => {
		expect(otherCockpits([PERSONAL, TEAM, SALES], "/team-cockpit/issues/list")).toEqual([PERSONAL, SALES])
	})

	it("offers nothing when the open cockpit is the only one", () => {
		expect(otherCockpits([TEAM], "/team-cockpit")).toEqual([])
		expect(otherCockpits([], "/team-cockpit")).toEqual([])
		expect(otherCockpits(undefined, "/team-cockpit")).toEqual([])
	})

	it("skips entries without a route and falls back to the route as title", () => {
		expect(otherCockpits([{ title: "Broken" }, { route: "/sales-cockpit" }], "/team-cockpit")).toEqual([
			{ route: "/sales-cockpit", title: "/sales-cockpit" },
		])
	})
})
