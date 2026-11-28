// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import { chartLegend, chartMode, chartValues, YEAR_EARLIER_OPACITY } from "./leadChart.js"

const month = {
	count: 7,
	split: { Inbound: 3, Outbound: 2, none: 2 },
	last_year: 5,
	last_year_split: { Inbound: 1, Outbound: 4, none: 0 },
}

describe("lead overview chart (phamos/phamos#1950)", () => {
	it("defaults to side by side and ignores unknown stored values", () => {
		expect(chartMode(undefined)).toBe("side")
		expect(chartMode("bogus")).toBe("side")
		expect(chartMode("stacked")).toBe("stacked")
	})

	it("side by side puts each direction and the total next to its year-earlier value", () => {
		const bars = chartValues(month, "side")
		expect(bars.map((b) => b.value)).toEqual([3, 1, 2, 4, 7, 5])
		expect(bars.map((b) => b.opacity)).toEqual([1, YEAR_EARLIER_OPACITY, 1, YEAR_EARLIER_OPACITY, 1, YEAR_EARLIER_OPACITY])
		// Pairs share a colour; the total is the month's count, Not set included.
		expect(bars[0].color).toBe(bars[1].color)
		expect(bars[4].label).toBe("Total")
		expect(bars[5].label).toBe("Total · Same month a year earlier")
	})

	it("stacked keeps two bars of three segments each", () => {
		const [now, before] = chartValues(month, "stacked")
		expect(now.map((s) => s.value)).toEqual([3, 2, 2])
		expect(before.map((s) => s.value)).toEqual([1, 4, 0])
		expect(before.every((s) => s.opacity === YEAR_EARLIER_OPACITY)).toBe(true)
	})

	it("draws no year-earlier bars without history", () => {
		const fresh = { ...month, last_year: null, last_year_split: null }
		const side = chartValues(fresh, "side")
		expect([side[1], side[3], side[5]].map((b) => b.value)).toEqual([0, 0, 0])
		expect(chartValues(fresh, "stacked")[1].map((s) => s.value)).toEqual([0, 0, 0])
	})

	it("names Total in the side-by-side legend and Not set in the stacked one", () => {
		expect(chartLegend("side").map((l) => l.label)).toEqual(["Inbound", "Outbound", "Total"])
		expect(chartLegend("stacked").map((l) => l.label)).toEqual(["Inbound", "Outbound", "Not set"])
	})
})
