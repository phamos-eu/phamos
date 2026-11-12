// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import { createdRangeLabel, leadDeskListUrl, leadFilterChips, leadFiltersFromQuery } from "./leadFilters.js"

describe("lead overview filters in the URL", () => {
	it("keeps only the known, non-empty keys", () => {
		expect(leadFiltersFromQuery({ created_from: "2026-11-01", status: "", foo: "bar", source: "none" })).toEqual({
			created_from: "2026-11-01",
			source: "none",
		})
	})

	it("names a whole month by its name and other ranges by their days", () => {
		expect(createdRangeLabel("2026-11-01", "2026-11-30")).toBe("Nov 2026")
		expect(createdRangeLabel("2028-02-01", "2028-02-29")).toBe("Feb 2028")
		expect(createdRangeLabel("2026-11-01", "2026-11-12")).toBe("1 Nov 2026 – 12 Nov 2026")
	})

	it("turns the created range into one chip and 'none' into 'not set'", () => {
		const chips = leadFilterChips({ created_from: "2026-11-01", created_to: "2026-11-30", direction: "none", source: "none" })
		expect(chips.map((c) => c.label)).toEqual(["Created: Nov 2026", "Inbound / Outbound: not set", "No source"])
		expect(chips[0].keys).toEqual(["created_from", "created_to"])
	})
})

describe("Desk list URL", () => {
	it("passes the same filters to Desk's Lead list", () => {
		const url = leadDeskListUrl({ created_from: "2026-11-01", created_to: "2026-11-12", direction: "Inbound", source: "none" })
		const params = new URL(url, "https://erp.example.com").searchParams
		expect(JSON.parse(params.get("creation"))).toEqual(["Between", ["2026-11-01", "2026-11-12"]])
		expect(params.get("custom_lead_direction")).toBe("Inbound")
		expect(JSON.parse(params.get("source"))).toEqual(["is", "not set"])
	})

	it("is the plain list without filters", () => {
		expect(leadDeskListUrl({})).toBe("/app/lead")
	})
})
