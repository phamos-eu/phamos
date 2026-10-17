// Layout of the My Day timeline (#1573): one time axis running down through the days, where
// time with something in it is drawn to scale and empty time is squeezed. Pure functions; times
// are local Date objects (convert server datetimes with parseSystemDatetimeToUserDate first).

import { __ } from "./i18n.js"

export const PX_PER_MINUTE = 2
export const PAD_MINUTES = 15
export const GAP_COLLAPSE_MINUTES = 30
export const GAP_ROW_PX = 28
export const MIN_BLOCK_PX = 6
// Labels of points (check-ins, ToDos) are one line; closer points are pushed apart.
export const POINT_ROW_PX = 22
const DAY_MINUTES = 24 * 60

const pad = (n) => String(n).padStart(2, "0")

export function dayKey(date) {
	return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function minuteOfDay(date) {
	return date.getHours() * 60 + date.getMinutes() + date.getSeconds() / 60
}

function startOfNextDay(date) {
	return new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1)
}

// Put items on the days they touch: { "2026-10-13": [{ ...item, start, end }] } in minutes of that
// day. An item without an end runs until `now` (a running timer); items crossing midnight are cut
// and marked as continuing.
export function splitIntoDays(items, now) {
	const days = {}
	for (const item of items) {
		if (!item.start) continue
		let from = item.start
		const point = item.kind === "point"
		const until = point ? item.start : item.end || now || item.start
		let first = true
		while (from <= until) {
			const nextDay = startOfNextDay(from)
			const to = until < nextDay ? until : nextDay
			const key = dayKey(from)
			const startMinute = minuteOfDay(from)
			const endMinute = to === nextDay ? DAY_MINUTES : minuteOfDay(to)
			;(days[key] ||= []).push({
				...item,
				start: startMinute,
				end: point ? startMinute : Math.max(endMinute, startMinute),
				continuesBefore: !first,
				continuesAfter: to === nextDay && until > nextDay,
				running: !point && !item.end && to === until,
			})
			if (to === until) break
			from = nextDay
			first = false
		}
	}
	return days
}

function hourLabel(minute) {
	return `${pad(Math.floor(minute / 60) % 24)}:00`
}

// Rows for one day: spans drawn to scale around the events, and gap rows for empty stretches
// longer than GAP_COLLAPSE_MINUTES. `now` (minutes) keeps the present visible on today.
export function layoutDay(events, { now = null } = {}) {
	const marks = events.map((e) => ({ start: e.start, end: Math.max(e.end ?? e.start, e.start) }))
	if (now !== null) marks.push({ start: now, end: now })
	if (!marks.length) return { rows: [], height: 0 }

	const windows = marks
		.map((m) => ({ start: Math.max(0, m.start - PAD_MINUTES), end: Math.min(DAY_MINUTES, m.end + PAD_MINUTES) }))
		.sort((a, b) => a.start - b.start)
	const spans = []
	for (const w of windows) {
		const last = spans[spans.length - 1]
		if (last && w.start - last.end <= GAP_COLLAPSE_MINUTES) last.end = Math.max(last.end, w.end)
		else spans.push({ ...w })
	}

	const rows = []
	spans.forEach((span, index) => {
		if (index > 0) {
			const minutes = span.start - spans[index - 1].end
			rows.push({ kind: "gap", start: spans[index - 1].end, end: span.start, minutes, height: GAP_ROW_PX })
		}
		const inSpan = events.filter((e) => e.start >= span.start && e.start <= span.end)
		const blocks = inSpan.filter((e) => e.kind !== "point").sort((a, b) => a.start - b.start)
		const laneEnds = []
		const placed = blocks.map((block) => {
			let lane = laneEnds.findIndex((end) => end <= block.start)
			if (lane === -1) lane = laneEnds.push(block.end) - 1
			else laneEnds[lane] = block.end
			return {
				...block,
				lane,
				top: (block.start - span.start) * PX_PER_MINUTE,
				height: Math.max((block.end - block.start) * PX_PER_MINUTE, MIN_BLOCK_PX),
			}
		})
		// Points at nearly the same time would overlap: keep at least POINT_ROW_PX between them,
		// starting half a row below the span's top, and grow the span when they need the room.
		let previous = POINT_ROW_PX / 2 - POINT_ROW_PX
		const points = inSpan
			.filter((e) => e.kind === "point")
			.sort((a, b) => a.start - b.start)
			.map((point) => {
				const exact = (point.start - span.start) * PX_PER_MINUTE
				const top = Math.max(exact, previous + POINT_ROW_PX)
				previous = top
				return { ...point, top, exactTop: exact, shifted: top !== exact }
			})
		const height = Math.max((span.end - span.start) * PX_PER_MINUTE, points.length ? previous + POINT_ROW_PX / 2 : 0)
		const hours = []
		for (let m = Math.ceil(span.start / 60) * 60; m <= span.end; m += 60) {
			hours.push({ label: hourLabel(m), top: (m - span.start) * PX_PER_MINUTE })
		}
		rows.push({
			kind: "span",
			start: span.start,
			end: span.end,
			height,
			blocks: placed,
			points,
			hours,
			lanes: Math.max(laneEnds.length, 1),
			nowTop: now !== null && now >= span.start && now <= span.end ? (now - span.start) * PX_PER_MINUTE : null,
		})
	})
	return { rows, height: rows.reduce((sum, row) => sum + row.height, 0) }
}

export function formatGap(minutes) {
	const total = Math.round(minutes)
	const h = Math.floor(total / 60)
	const m = total % 60
	if (!h) return __("{0} min", [m])
	return m ? __("{0} h {1} min", [h, m]) : __("{0} h", [h])
}
