// Run with `yarn test:spa` (vitest globals, see personal_frontend/vitest.config.js).
import { listAppointments, nextOccurrence, occurrencesBetween, parseDateTime, weeklyDays } from "./appointments.js"

const day = (iso) => parseDateTime(iso)
const starts = (list) =>
	list.map(({ start }) => `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, "0")}-${String(start.getDate()).padStart(2, "0")}`)

const appt = (extra = {}) => ({
	name: "A",
	subject: "All-hands",
	start: "2026-12-01 10:00:00", // a Tuesday
	end: "2026-12-01 11:00:00",
	repeat_this_event: 0,
	...extra,
})

describe("appointment occurrences", () => {
	it("a single appointment occurs once, with its duration", () => {
		const [only] = occurrencesBetween(appt(), day("2026-11-01"), day("2026-12-31"))
		expect(only.end - only.start).toBe(60 * 60 * 1000)
		expect(occurrencesBetween(appt(), day("2027-01-01"), day("2027-01-31"))).toEqual([])
	})

	it("weekly repeats on the ticked weekdays until repeat_till (inclusive)", () => {
		const a = appt({ repeat_this_event: 1, repeat_on: "Weekly", tuesday: 1, thursday: 1, repeat_till: "2026-12-10" })
		expect(starts(occurrencesBetween(a, day("2026-11-01"), day("2026-12-31")))).toEqual([
			"2026-12-01",
			"2026-12-03",
			"2026-12-08",
			"2026-12-10",
		])
	})

	it("weekly without ticked days uses the start's weekday", () => {
		expect(weeklyDays(appt({ repeat_this_event: 1, repeat_on: "Weekly" }))).toEqual([1])
	})

	it("monthly skips months without the start's day", () => {
		const a = appt({ start: "2027-01-31 09:00:00", end: "2027-01-31 10:00:00", repeat_this_event: 1, repeat_on: "Monthly" })
		expect(starts(occurrencesBetween(a, day("2027-01-01"), day("2027-05-31 23:59:59")))).toEqual([
			"2027-01-31",
			"2027-03-31",
			"2027-05-31",
		])
	})

	it("daily and yearly", () => {
		const daily = appt({ repeat_this_event: 1, repeat_on: "Daily", repeat_till: "2026-12-03" })
		expect(starts(occurrencesBetween(daily, day("2026-11-01"), day("2026-12-31")))).toEqual([
			"2026-12-01",
			"2026-12-02",
			"2026-12-03",
		])
		const yearly = appt({ repeat_this_event: 1, repeat_on: "Yearly" })
		expect(starts(occurrencesBetween(yearly, day("2026-01-01"), day("2028-12-31")))).toEqual([
			"2026-12-01",
			"2027-12-01",
			"2028-12-01",
		])
	})

	it("ignores the repeat options when repeat is off or unknown", () => {
		const a = appt({ repeat_this_event: 0, repeat_on: "Daily" })
		expect(occurrencesBetween(a, day("2026-11-01"), day("2026-12-31"))).toHaveLength(1)
	})
})

describe("appointment list", () => {
	const now = day("2026-12-05 12:00:00")

	it("finds the next occurrence of a repeat", () => {
		const a = appt({ repeat_this_event: 1, repeat_on: "Weekly", tuesday: 1 })
		expect(starts([nextOccurrence(a, now)])).toEqual(["2026-12-08"])
	})

	it("lists upcoming by next occurrence; past ones only on request, newest first", () => {
		const weekly = appt({ name: "W", repeat_this_event: 1, repeat_on: "Weekly", tuesday: 1 })
		const soon = appt({ name: "S", start: "2026-12-06 09:00:00", end: "2026-12-06 10:00:00" })
		const old = appt({ name: "O", start: "2026-11-01 09:00:00", end: "2026-11-01 10:00:00" })
		const older = appt({ name: "OO", start: "2026-10-01 09:00:00", end: "2026-10-01 10:00:00" })
		expect(listAppointments([weekly, old, soon, older], now).map((i) => i.appointment.name)).toEqual(["S", "W"])
		expect(listAppointments([weekly, old, soon, older], now, true).map((i) => i.appointment.name)).toEqual([
			"S",
			"W",
			"O",
			"OO",
		])
	})
})

describe("long-running repeats (AI review of !1203)", () => {
	it("a daily repeat without an end still occurs after more than 13 years", () => {
		const a = appt({ repeat_this_event: 1, repeat_on: "Daily" })
		const from = day("2041-06-01")
		expect(starts(occurrencesBetween(a, from, day("2041-06-02 23:59:59")))).toEqual(["2041-06-01", "2041-06-02"])
		expect(nextOccurrence(a, from, 3)).not.toBeNull()
	})

	it("weekly and monthly repeats start right at the window, years later", () => {
		const weekly = appt({ repeat_this_event: 1, repeat_on: "Weekly", tuesday: 1 })
		expect(starts(occurrencesBetween(weekly, day("2040-01-01"), day("2040-01-14")))).toEqual(["2040-01-03", "2040-01-10"])
		const monthly = appt({ repeat_this_event: 1, repeat_on: "Monthly" })
		expect(starts(occurrencesBetween(monthly, day("2045-03-01"), day("2045-04-30")))).toEqual(["2045-03-01", "2045-04-01"])
	})

	it("an occurrence that started before the window but still runs is included", () => {
		const long = appt({ start: "2026-12-01 22:00:00", end: "2026-12-02 02:00:00", repeat_this_event: 1, repeat_on: "Daily" })
		expect(starts(occurrencesBetween(long, day("2026-12-05 01:00:00"), day("2026-12-05 01:30:00")))).toEqual(["2026-12-04"])
	})
})
