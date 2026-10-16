// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import { formatGap, GAP_ROW_PX, layoutDay, POINT_ROW_PX, PX_PER_MINUTE, splitIntoDays } from "./timelineLayout.js"

const at = (day, hh, mm = 0) => new Date(2026, 9, day, hh, mm)

describe("timeline layout", () => {
	it("draws busy time to scale with padding", () => {
		const { rows } = layoutDay([{ id: "a", kind: "block", start: 9 * 60, end: 10 * 60 }])
		expect(rows).toHaveLength(1)
		expect(rows[0]).toMatchObject({ kind: "span", start: 8 * 60 + 45, end: 10 * 60 + 15 })
		expect(rows[0].height).toBe(90 * PX_PER_MINUTE)
		expect(rows[0].blocks[0]).toMatchObject({ top: 15 * PX_PER_MINUTE, height: 60 * PX_PER_MINUTE, lane: 0 })
		expect(rows[0].hours.map((h) => h.label)).toEqual(["09:00", "10:00"])
	})

	it("squeezes gaps over 30 minutes into one row and keeps short ones", () => {
		const { rows } = layoutDay([
			{ id: "in", kind: "point", start: 8 * 60, end: 8 * 60 },
			{ id: "todo", kind: "point", start: 8 * 60 + 50, end: 8 * 60 + 50 },
			{ id: "out", kind: "point", start: 17 * 60, end: 17 * 60 },
		])
		expect(rows.map((r) => r.kind)).toEqual(["span", "gap", "span"])
		expect(rows[0].points.map((p) => p.id)).toEqual(["in", "todo"])
		expect(rows[1]).toMatchObject({ minutes: 16 * 60 + 45 - (9 * 60 + 5), height: GAP_ROW_PX })
	})

	it("puts overlapping blocks in lanes", () => {
		const { rows } = layoutDay([
			{ id: "a", kind: "block", start: 600, end: 660 },
			{ id: "b", kind: "block", start: 630, end: 700 },
			{ id: "c", kind: "block", start: 670, end: 690 },
		])
		expect(rows[0].blocks.map((b) => b.lane)).toEqual([0, 1, 0])
		expect(rows[0].lanes).toBe(2)
	})

	it("shows the now line and an empty day as nothing", () => {
		expect(layoutDay([]).rows).toEqual([])
		const { rows } = layoutDay([], { now: 12 * 60 })
		expect(rows[0].nowTop).toBe(15 * PX_PER_MINUTE)
	})

	it("splits a block over midnight and runs an open one until now", () => {
		const days = splitIntoDays(
			[
				{ id: "night", kind: "block", start: at(12, 23), end: at(13, 1) },
				{ id: "running", kind: "block", start: at(13, 14), end: null },
				{ id: "in", kind: "point", start: at(13, 8), end: null },
			],
			at(13, 15, 30)
		)
		expect(days["2026-10-12"]).toEqual([expect.objectContaining({ id: "night", start: 1380, end: 1440, continuesAfter: true })])
		const day = days["2026-10-13"]
		expect(day.find((e) => e.id === "night")).toMatchObject({ start: 0, end: 60, continuesBefore: true })
		expect(day.find((e) => e.id === "running")).toMatchObject({ start: 840, end: 930, running: true })
		expect(day.find((e) => e.id === "in")).toMatchObject({ start: 480, end: 480 })
	})

	it("keeps a point on its own day", () => {
		const days = splitIntoDays([{ id: "in", kind: "point", start: at(12, 8), end: null }], at(14, 9))
		expect(Object.keys(days)).toEqual(["2026-10-12"])
	})

	it("pushes points that are close in time apart", () => {
		const { rows } = layoutDay([
			{ id: "a", kind: "point", start: 23 * 60 + 1, end: 23 * 60 + 1 },
			{ id: "b", kind: "point", start: 23 * 60 + 3, end: 23 * 60 + 3 },
			{ id: "c", kind: "point", start: 23 * 60 + 3, end: 23 * 60 + 3 },
		])
		const tops = rows[0].points.map((p) => p.top)
		expect(tops[1] - tops[0]).toBeGreaterThanOrEqual(POINT_ROW_PX)
		expect(tops[2] - tops[1]).toBeGreaterThanOrEqual(POINT_ROW_PX)
		expect(rows[0].height).toBeGreaterThanOrEqual(tops[2] + POINT_ROW_PX / 2)
	})

	it("labels gaps", () => {
		expect(formatGap(25)).toBe("25 min")
		expect(formatGap(120)).toBe("2 h")
		expect(formatGap(130)).toBe("2 h 10 min")
	})
})
