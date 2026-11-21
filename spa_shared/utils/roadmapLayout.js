// Layout math for the read-only RoadmapGantt (#2034): plain data in, pixel positions out.
// No DOM and no Vue, so it is unit-tested (roadmapLayout.test.js) and TaskGantt can adopt it later.
// Positions build on the day columns of buildTimeline (ganttTimeline.js).

import { buildTimeline } from "./ganttTimeline.js"
import { formatDateIso } from "./ganttTimelineFormat.js"
import { orthogonalDependencyPath } from "./ganttDependencyArrows.js"

/** Width of one day column in px per zoom: a week ≈ 140 px, a month ≈ 180 px, a quarter ≈ 180 px. */
export const ZOOM_DAY_WIDTH = { week: 20, month: 6, quarter: 2 }

/** Row geometry in px: padding, the strip with the feature dots, and one lane per overlapping bar. */
export const ROW_PADDING = 3
export const EVENT_STRIP = 14
export const LANE_HEIGHT = 22

// orthogonalDependencyPath routes the vertical part of an arrow 10 px + lane × 8 px right of
// its start; two vertical parts closer than this would draw on top of each other.
const ROUTE_BASE = 10
const ROUTE_STEP = 8

const DAY_MS = 86400000

/** A Date at local midnight from a Date or a "YYYY-MM-DD" string ("2026-11-21" is not read as UTC). */
export function toDay(value) {
	if (!value) return null
	if (value instanceof Date) {
		if (Number.isNaN(value.getTime())) return null
		return new Date(value.getFullYear(), value.getMonth(), value.getDate())
	}
	const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value))
	if (!match) return null
	return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
}

/** "YYYY-MM-DD" of a Date or date string, for formatDate; "" without a date. */
export function isoDay(value) {
	const day = toDay(value)
	return day ? formatDateIso(day) : ""
}

function dayDiff(from, to) {
	// Rounded, so a daylight-saving change in between doesn't shift a day by an hour.
	return Math.round((to - from) / DAY_MS)
}

function columnWidth(timeline) {
	return timeline?.days?.[0]?.width || 0
}

/** The timeline for a date range at one of the three zooms. */
export function roadmapTimeline(range, zoom = "month") {
	const width = ZOOM_DAY_WIDTH[zoom] || ZOOM_DAY_WIDTH.month
	return buildTimeline(toDay(range?.start), toDay(range?.end), width, width)
}

/** Left edge in px of the day `date` on the timeline; null without a date. Not clipped to the range. */
export function dateToX(timeline, date) {
	const day = toDay(date)
	if (!day || !timeline?.rangeStart) return null
	return dayDiff(timeline.rangeStart, day) * columnWidth(timeline)
}

/**
 * Left and width in px of a bar from `start` to `end` (both days inclusive), clipped to the
 * timeline. Null when a date is missing or the bar lies outside the range.
 * `clippedStart` / `clippedEnd` say the bar goes on beyond the visible range.
 */
export function barRect(timeline, start, end) {
	const startX = dateToX(timeline, start)
	const endX = dateToX(timeline, end)
	if (startX === null || endX === null) return null
	// Swapped dates draw the same span as rowHeights packs, not a one-day bar.
	const left = Math.min(startX, endX)
	const right = Math.max(startX, endX) + columnWidth(timeline)
	const visibleLeft = Math.max(0, left)
	const visibleRight = Math.min(timeline.totalWidth, right)
	if (visibleRight <= visibleLeft) return null
	return {
		left: visibleLeft,
		width: visibleRight - visibleLeft,
		clippedStart: left < 0,
		clippedEnd: right > timeline.totalWidth,
	}
}

function isLevel(value) {
	return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value))
}

/**
 * Filled share (0 … 1) of a level-step bar "L{from} → L{target}" at level `current`:
 * L2 → L4 at level 3 is 0.5. Null without levels (no fill drawn).
 */
export function levelFill(current, target, from) {
	if (!isLevel(target) || !isLevel(from)) return null
	const lo = Number(from)
	const hi = Number(target)
	const now = isLevel(current) ? Number(current) : lo
	if (hi <= lo) return now >= hi ? 1 : 0
	return Math.min(1, Math.max(0, (now - lo) / (hi - lo)))
}

/**
 * Groups the dots of one row that would overlap: a dot closer than `minGapPx` to the first dot
 * of the current group joins it. A group sits at the middle of its dots and carries their count.
 * Status: "planned" or "finished" when all dots agree, otherwise "mixed".
 * `key` is unique within the row even when one feature has a planned and a finished dot
 * (both carry the feature's name); `name` is the first event's, for selecting.
 * Events without a date or outside the timeline are left out.
 */
export function stackEvents(events, timeline, minGapPx = 10) {
	const placed = []
	for (const event of events || []) {
		const x = dateToX(timeline, event.date)
		if (x === null || x < 0 || x >= timeline.totalWidth) continue
		placed.push({ event, x: x + columnWidth(timeline) / 2 })
	}
	placed.sort((a, b) => a.x - b.x || String(a.event.name).localeCompare(String(b.event.name)))

	const groups = []
	for (const item of placed) {
		const group = groups[groups.length - 1]
		if (group && item.x - group.firstX < minGapPx) {
			group.items.push(item)
		} else {
			groups.push({ firstX: item.x, items: [item] })
		}
	}

	return groups.map(({ items }) => {
		const evs = items.map((i) => i.event)
		const statuses = new Set(evs.map((e) => (e.status === "finished" ? "finished" : "planned")))
		return {
			key: evs.map((e) => `${e.name}@${isoDay(e.date)}`).join("|"),
			name: evs[0].name,
			x: items.reduce((sum, i) => sum + i.x, 0) / items.length,
			count: evs.length,
			status: statuses.size === 1 ? [...statuses][0] : "mixed",
			events: evs,
		}
	})
}

/** Quarter header segments ("Q4 2026") of a timeline, like its `months` and `weeks`. */
export function quarterSegments(timeline) {
	const quarters = []
	for (const day of timeline?.days || []) {
		const year = day.date.getFullYear()
		const quarter = Math.floor(day.date.getMonth() / 3) + 1
		const key = `${year}-Q${quarter}`
		const last = quarters[quarters.length - 1]
		if (!last || last.key !== key) {
			quarters.push({ key, year, quarter, left: day.left, width: day.width, startIso: day.iso, endIso: day.iso })
		} else {
			last.width += day.width
			last.endIso = day.iso
		}
	}
	return quarters
}

function overlaps(a, b) {
	return a.start <= b.end && b.start <= a.end
}

/**
 * Height and top of every row. A row has one lane for its bars; it grows by a lane only where
 * bars overlap in time (a staircase), so many rows fit. Bars without dates take no lane.
 * Returns rows in order: { name, top, height, lanes, barLanes: { [barName]: laneIndex } }.
 */
export function rowHeights(rows) {
	let top = 0
	return (rows || []).map((row) => {
		const spans = []
		for (const bar of row.bars || []) {
			const start = toDay(bar.start)
			const end = toDay(bar.end)
			if (!start || !end) continue
			spans.push({ name: bar.name, start: Math.min(start, end), end: Math.max(start, end) })
		}
		spans.sort((a, b) => a.start - b.start || a.end - b.end)

		// Greedy lane packing: each bar takes the first lane where it overlaps nothing.
		const laneSpans = []
		const barLanes = {}
		for (const span of spans) {
			let lane = laneSpans.findIndex((taken) => !taken.some((other) => overlaps(other, span)))
			if (lane === -1) {
				lane = laneSpans.length
				laneSpans.push([])
			}
			laneSpans[lane].push(span)
			barLanes[span.name] = lane
		}

		const lanes = Math.max(1, laneSpans.length)
		const height = ROW_PADDING * 2 + EVENT_STRIP + lanes * LANE_HEIGHT
		const layout = { name: row.name, top, height, lanes, barLanes }
		top += height
		return layout
	})
}

/**
 * SVG paths for the dependency arrows, from the right middle of the predecessor bar to the
 * left middle of the successor. `bars` maps a bar name to { left, width, top, height, critical }.
 * Each arrow gets the lowest lane whose vertical part doesn't run on top of another arrow's,
 * so arrows leaving the same bar never overlap. Dependencies with a missing bar are skipped.
 * Returns [{ from, to, conflict, critical, lane, d }]; `critical` when either end is critical.
 */
export function dependencyPaths(bars, dependencies) {
	const placed = []
	for (const dep of dependencies || []) {
		const from = bars?.[dep.from]
		const to = bars?.[dep.to]
		if (!from || !to) continue
		const startX = from.left + from.width
		const startY = from.top + from.height / 2
		const endX = to.left
		const endY = to.top + to.height / 2
		const yLow = Math.min(startY, endY)
		const yHigh = Math.max(startY, endY)

		let lane = 0
		const clashes = (l) =>
			placed.some((other) => {
				const sameColumn = Math.abs(other.routeX - (startX + ROUTE_BASE + l * ROUTE_STEP)) < ROUTE_STEP
				return sameColumn && other.yLow <= yHigh && yLow <= other.yHigh
			})
		while (clashes(lane)) lane += 1

		placed.push({
			from: dep.from,
			to: dep.to,
			conflict: Boolean(dep.conflict),
			critical: Boolean(from.critical || to.critical),
			lane,
			routeX: startX + ROUTE_BASE + lane * ROUTE_STEP,
			yLow,
			yHigh,
			d: orthogonalDependencyPath(startX, startY, endX, endY, lane),
		})
	}
	return placed.map(({ from, to, conflict, critical, lane, d }) => ({ from, to, conflict, critical, lane, d }))
}
