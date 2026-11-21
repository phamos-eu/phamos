// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import {
	barRect,
	dateToX,
	dependencyPaths,
	EVENT_STRIP,
	LANE_HEIGHT,
	levelFill,
	quarterSegments,
	roadmapTimeline,
	ROW_PADDING,
	rowHeights,
	stackEvents,
} from "./roadmapLayout.js"

// Month zoom: 6 px per day, starting 1 Nov 2026.
const timeline = roadmapTimeline({ start: "2026-11-01", end: "2027-03-31" }, "month")

describe("positions on the timeline", () => {
	it("puts a date at its day column, read as a local date", () => {
		expect(dateToX(timeline, "2026-11-01")).toBe(0)
		expect(dateToX(timeline, "2026-11-11")).toBe(60)
		expect(dateToX(timeline, null)).toBeNull()
	})

	it("draws a bar over both its first and its last day", () => {
		expect(barRect(timeline, "2026-11-11", "2026-11-20")).toMatchObject({ left: 60, width: 60 })
	})

	it("clips a bar to the range and drops one outside it", () => {
		expect(barRect(timeline, "2026-10-01", "2026-11-05")).toMatchObject({ left: 0, width: 30, clippedStart: true })
		expect(barRect(timeline, "2027-05-01", "2027-06-01")).toBeNull()
	})

	it("draws swapped dates as the same span", () => {
		expect(barRect(timeline, "2026-11-20", "2026-11-11")).toMatchObject({ left: 60, width: 60 })
	})
})

describe("levelFill", () => {
	it("fills a L2 → L4 bar by the current level", () => {
		expect(levelFill(2, 4, 2)).toBe(0)
		expect(levelFill(3, 4, 2)).toBe(0.5)
		expect(levelFill(4, 4, 2)).toBe(1)
	})

	it("draws no fill without levels", () => {
		expect(levelFill(3, null, null)).toBeNull()
		expect(levelFill(3, 4, undefined)).toBeNull()
	})

	it("stays between empty and full", () => {
		expect(levelFill(1, 4, 2)).toBe(0)
		expect(levelFill(5, 4, 2)).toBe(1)
		expect(levelFill(null, 4, 2)).toBe(0)
	})
})

describe("stackEvents", () => {
	const ev = (name, date, status = "planned") => ({ name, date, status })

	it("groups dots closer than the gap and keeps the others apart", () => {
		// 6 px per day: 1, 2 and 3 Nov lie within 12 px of each other; 20 Nov is far away.
		const stacks = stackEvents(
			[ev("F-3", "2026-11-03", "finished"), ev("F-1", "2026-11-01"), ev("F-2", "2026-11-02"), ev("F-9", "2026-11-20")],
			timeline,
			14
		)
		expect(stacks.map((s) => s.count)).toEqual([3, 1])
		expect(stacks[0].events.map((e) => e.name)).toEqual(["F-1", "F-2", "F-3"])
		expect(stacks[0].status).toBe("mixed")
		expect(stacks[0].x).toBe(9) // middle of 3, 9 and 15
		expect(stacks[1]).toMatchObject({ name: "F-9", count: 1, status: "planned" })
	})

	it("keeps a feature's planned and finished dots apart by key", () => {
		const stacks = stackEvents([ev("F-1", "2026-11-01"), ev("F-1", "2026-12-15", "finished")], timeline, 14)
		expect(stacks.map((s) => s.name)).toEqual(["F-1", "F-1"])
		expect(stacks[0].key).not.toBe(stacks[1].key)
	})

	it("leaves out dots without a date or outside the range", () => {
		expect(stackEvents([ev("A", null), ev("B", "2025-01-01")], timeline, 10)).toEqual([])
	})
})

describe("quarterSegments", () => {
	it("splits the timeline into quarters across a year boundary", () => {
		const quarters = quarterSegments(timeline)
		expect(quarters.map((q) => [q.year, q.quarter])).toEqual([
			[2026, 4],
			[2027, 1],
		])
		// 61 days of Nov–Dec, then 90 days of Jan–Mar, at 6 px each.
		expect(quarters.map((q) => [q.left, q.width])).toEqual([
			[0, 366],
			[366, 540],
		])
		expect(quarters[1]).toMatchObject({ startIso: "2027-01-01", endIso: "2027-03-31" })
	})
})

describe("dependencyPaths", () => {
	const bar = (left, width, top, extra = {}) => ({ left, width, top, height: 14, ...extra })

	it("gives each arrow leaving the same bar its own lane", () => {
		const bars = { A: bar(0, 60, 0), B: bar(100, 30, 40), C: bar(100, 30, 80) }
		const paths = dependencyPaths(bars, [
			{ from: "A", to: "B" },
			{ from: "A", to: "C" },
		])
		expect(paths.map((p) => p.lane)).toEqual([0, 1])
		expect(new Set(paths.map((p) => p.d)).size).toBe(2)
		expect(paths[0].d.startsWith("M 60 7 H 70 V 47 H 100")).toBe(true)
	})

	it("keeps lane 0 for arrows that don't meet and skips missing bars", () => {
		const bars = { A: bar(0, 60, 0), B: bar(100, 30, 40), C: bar(300, 30, 0, { critical: true }), D: bar(400, 30, 40) }
		const paths = dependencyPaths(bars, [
			{ from: "A", to: "B" },
			{ from: "C", to: "D", conflict: true },
			{ from: "A", to: "GONE" },
		])
		expect(paths.map((p) => [p.from, p.to, p.lane, p.conflict, p.critical])).toEqual([
			["A", "B", 0, false, false],
			["C", "D", 0, true, true],
		])
	})
})

describe("rowHeights", () => {
	const oneLane = ROW_PADDING * 2 + EVENT_STRIP + LANE_HEIGHT

	it("grows a row only for bars that overlap in time", () => {
		const rows = [
			{
				name: "Sales",
				bars: [
					{ name: "C1", start: "2026-11-01", end: "2026-11-30" },
					{ name: "C2", start: "2026-12-01", end: "2026-12-31" },
				],
			},
			{
				name: "HR",
				bars: [
					{ name: "C3", start: "2026-11-01", end: "2026-12-15" },
					{ name: "C4", start: "2026-12-01", end: "2027-01-31" },
					{ name: "C5", start: "2027-01-01", end: "2027-02-28" },
				],
			},
			{ name: "No module", bars: [] },
		]
		const layout = rowHeights(rows)
		expect(layout.map((r) => r.lanes)).toEqual([1, 2, 1])
		expect(layout[0].height).toBe(oneLane)
		expect(layout[1].height).toBe(oneLane + LANE_HEIGHT)
		expect(layout[1].barLanes).toEqual({ C3: 0, C4: 1, C5: 0 })
		expect(layout.map((r) => r.top)).toEqual([0, oneLane, oneLane * 2 + LANE_HEIGHT])
	})
})
