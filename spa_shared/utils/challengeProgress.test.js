// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import {
	dayState,
	finishedText,
	jokerText,
	progressText,
	repairText,
	ringFraction,
	streakText,
	suggestionText,
	todayText,
	welcomeText,
} from "./challengeProgress.js"

const base = {
	working_days: 10,
	counted_days: 3,
	jokers_left: 1,
	current_streak: 3,
	status: "Active",
	welcome_back: false,
	not_started: false,
	start_date: "2026-10-19",
	today: { in_schedule: true, closes: 1, target: 2, remaining: 1, repair: null },
}

describe("challenge progress", () => {
	it("counts up until half, then counts down", () => {
		expect(progressText(base)).toBe("3 of 10 days done")
		expect(progressText({ ...base, counted_days: 7 })).toBe("3 days to go")
		expect(progressText({ ...base, counted_days: 9 })).toBe("1 day to go")
		expect(progressText({ ...base, counted_days: 10 })).toBe("All days done")
		expect(ringFraction({ ...base, counted_days: 12 })).toBe(1)
	})

	it("describes today", () => {
		expect(todayText(base)).toBe("Today: 1 of 2 closed, 1 to go.")
		expect(todayText({ ...base, today: { ...base.today, remaining: 0 } })).toBe("Today counts. Nice work.")
		expect(todayText({ ...base, not_started: true })).toBe("Starts 2026-10-19.")
	})

	it("offers the repair only while it is still open", () => {
		const repairing = { ...base, today: { ...base.today, repair: { closes_needed: 3 } } }
		expect(repairText(repairing)).toBe("Close 3 today and the day before counts too.")
		expect(repairText({ ...repairing, today: { ...repairing.today, closes: 3 } })).toBe("")
	})

	it("shows a streak only from two days on", () => {
		expect(streakText({ ...base, current_streak: 1 })).toBe("")
		expect(streakText(base)).toBe("3 days in a row")
	})

	it("never scolds, whatever happens", () => {
		const forbidden = /fail|lost|reset|broke|shame|behind|missed/i
		const cases = [
			base,
			{ ...base, counted_days: 0, jokers_left: 0, current_streak: 0, welcome_back: true },
			{ ...base, status: "Ended", counted_days: 2 },
			{ ...base, status: "Completed", counted_days: 10 },
			{ ...base, today: { in_schedule: false } },
			{ ...base, today: { ...base.today, repair: { closes_needed: 4 } } },
		]
		const texts = cases.flatMap((c) => [
			progressText(c),
			todayText(c),
			repairText(c),
			welcomeText(c),
			jokerText(c),
			streakText(c),
			finishedText(c),
		])
		texts.push(...["Met", "Repaired", "Joker", "Missed", "Today", "Upcoming"].map((r) => dayState(r).label))
		texts.push(suggestionText({ baseline_per_day: 0 }), suggestionText({ baseline_per_day: 1.5, suggested: 2 }))
		for (const text of texts) expect(text).not.toMatch(forbidden)
	})
})
