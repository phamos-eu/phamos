// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import { actionLabel, caption, formatWorked, isUndoKey, liveWorkedMinutes, todayRows } from "./checkinSummary.js"

const checkedIn = {
	next_action: "OUT",
	stale_in: false,
	last: { name: "B", log_type: "IN", time: "2026-10-16 13:00:00" },
	today: {
		worked_minutes: 240,
		logs: [
			{ name: "A0", log_type: "IN", time: "2026-10-16 08:00:00" },
			{ name: "A1", log_type: "OUT", time: "2026-10-16 12:00:00" },
			{ name: "B", log_type: "IN", time: "2026-10-16 13:00:00" },
		],
	},
}
const time = (value) => value.slice(11, 16)
const day = () => "Thu"

describe("check-in summary", () => {
	it("advances the worked time only while checked in", () => {
		expect(liveWorkedMinutes(checkedIn, 125)).toBe(242)
		expect(liveWorkedMinutes({ ...checkedIn, next_action: "IN" }, 125)).toBe(240)
		expect(liveWorkedMinutes({ ...checkedIn, stale_in: true }, 125)).toBe(240)
		expect(liveWorkedMinutes(null)).toBe(0)
	})

	it("formats hours and minutes", () => {
		expect(formatWorked(0)).toBe("0 min")
		expect(formatWorked(59)).toBe("59 min")
		expect(formatWorked(120)).toBe("2 h")
		expect(formatWorked(252)).toBe("4 h 12 min")
	})

	it("labels the next action", () => {
		expect(actionLabel(checkedIn)).toEqual({ label: "Check out", icon: "log-out" })
		expect(actionLabel({ next_action: "IN" })).toEqual({ label: "Check in", icon: "log-in" })
	})

	it("describes the last log, with the day when it is from an earlier day", () => {
		expect(caption(checkedIn, time, day)).toBe("in since 13:00")
		expect(caption({ ...checkedIn, last: { log_type: "OUT", time: "2026-10-16 12:00:00" } }, time, day)).toBe(
			"out since 12:00"
		)
		expect(caption({ ...checkedIn, stale_in: true }, time, day)).toBe("in since Thu 13:00")
		expect(caption({ last: null }, time, day)).toBe("not checked in yet")
	})

	it("marks the open check-in as running", () => {
		expect(todayRows(checkedIn).map((row) => row.running)).toEqual([false, false, true])
		expect(todayRows({ ...checkedIn, next_action: "IN" }).some((row) => row.running)).toBe(false)
	})

	it("treats Ctrl/Cmd+Z outside text fields as undo", () => {
		const div = { tagName: "DIV" }
		expect(isUndoKey({ ctrlKey: true, key: "z", target: div })).toBe(true)
		expect(isUndoKey({ metaKey: true, key: "Z", target: div })).toBe(true)
		expect(isUndoKey({ ctrlKey: true, shiftKey: true, key: "z", target: div })).toBe(false)
		expect(isUndoKey({ ctrlKey: true, key: "z", target: { tagName: "INPUT" } })).toBe(false)
		expect(isUndoKey({ ctrlKey: true, key: "z", target: { tagName: "DIV", isContentEditable: true } })).toBe(false)
		expect(isUndoKey({ key: "z", target: div })).toBe(false)
	})
})
