import { describe, expect, it } from "vitest"
import { showTeamField, teamFieldLocked, teamOptions } from "./teamField.js"

describe("team field on the record pages (#1955)", () => {
	it("shows only when the server sends teams", () => {
		expect(showTeamField({ teams: ["Alpha"] })).toBe(true)
		expect(showTeamField({ teams: [] })).toBe(false)
		// the Team Cockpit sends no teams
		expect(showTeamField({})).toBe(false)
		expect(showTeamField(undefined)).toBe(false)
	})

	it("offers no team and the user's teams", () => {
		expect(teamOptions({ teams: ["Alpha"] }, "")).toEqual([
			{ label: "—", value: "" },
			{ label: "Alpha", value: "Alpha" },
		])
	})

	it("keeps another team's value visible and locks the field", () => {
		const options = { teams: ["Alpha"] }
		expect(teamOptions(options, "Beta").map((o) => o.value)).toEqual(["", "Alpha", "Beta"])
		expect(teamFieldLocked(options, "Beta")).toBe(true)
		expect(teamFieldLocked(options, "Alpha")).toBe(false)
		expect(teamFieldLocked(options, "")).toBe(false)
	})
})
