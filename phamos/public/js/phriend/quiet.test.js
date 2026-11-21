import { describe, expect, it } from "vitest"
import { FOREVER, HOUR_MS, end_of_today, is_quiet, may_react, back_in, warnings_muted } from "./quiet.js"

const now = new Date(2026, 10, 21, 14, 30).getTime()

describe("leave me in peace (#2010)", () => {
	it("is quiet until the time stored, or until called back", () => {
		expect(is_quiet(null, now)).toBe(false)
		expect(is_quiet({ quiet_until: now + HOUR_MS }, now)).toBe(true)
		expect(is_quiet({ quiet_until: now - 1 }, now)).toBe(false)
		expect(is_quiet({ quiet_until: FOREVER }, now)).toBe(true)
	})
	it("lets only the red warning through while quiet, and not while warnings are muted", () => {
		const q = { quiet_until: FOREVER }
		expect(may_react("heart", q, now)).toBe(false)
		expect(may_react("alert", q, now)).toBe(true)
		expect(may_react("alert", { ...q, warnings_muted_until: now + 60_000 }, now)).toBe(false)
		expect(may_react("alert", { warnings_muted_until: now - 1 }, now)).toBe(true)
		expect(may_react("heart", {}, now)).toBe(true)
		expect(warnings_muted({ warnings_muted_until: now + 1 }, now)).toBe(true)
	})
	it("ends 'for today' at local midnight", () => {
		expect(end_of_today(now)).toBe(new Date(2026, 10, 22, 0, 0).getTime())
	})
	it("comes back by itself only from a timed quiet", () => {
		expect(back_in({ quiet_until: now + 5000 }, now)).toBe(5000)
		expect(back_in({ quiet_until: FOREVER }, now)).toBe(null)
		expect(back_in({ quiet_until: now - 5 }, now)).toBe(null)
	})
})
