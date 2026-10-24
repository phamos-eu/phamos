import { describe, expect, it } from "vitest"
import {
	calendarBadge,
	formatLeaveDays,
	isSingleDay,
	leaveFormError,
	leavePayload,
	leaveStatusTheme,
} from "./leaveFormat.js"

const form = (values = {}) => ({ leave_type: "Vacation", from_date: "2026-11-03", to_date: "2026-11-05", ...values })

describe("leaveStatusTheme", () => {
	it("colours each status and falls back to gray", () => {
		expect(leaveStatusTheme("Open")).toBe("orange")
		expect(leaveStatusTheme("Approved")).toBe("green")
		expect(leaveStatusTheme("Rejected")).toBe("red")
		expect(leaveStatusTheme("Cancelled")).toBe("gray")
		expect(leaveStatusTheme("Something")).toBe("gray")
	})
})

describe("formatLeaveDays", () => {
	it("drops trailing zeros", () => {
		expect(formatLeaveDays(3)).toBe("3")
		expect(formatLeaveDays(2.5)).toBe("2.5")
		expect(formatLeaveDays("0.50")).toBe("0.5")
		expect(formatLeaveDays(undefined)).toBe("0")
	})
})

describe("isSingleDay", () => {
	it("compares from and to", () => {
		expect(isSingleDay({ from_date: "2026-11-03", to_date: "2026-11-03" })).toBe(true)
		expect(isSingleDay({ from_date: "2026-11-03", to_date: "2026-11-04" })).toBe(false)
		expect(isSingleDay(null)).toBe(false)
	})
})

describe("calendarBadge", () => {
	it("maps the Phase 2 calendar state", () => {
		expect(calendarBadge({ state: "synced" }).theme).toBe("green")
		expect(calendarBadge({ state: "pending" }).theme).toBe("blue")
		expect(calendarBadge({ state: "error", error: "No DAV app password" })).toEqual({
			key: "Not in my calendar",
			theme: "orange",
			title: "No DAV app password",
		})
		expect(calendarBadge({ state: "none" })).toBeNull()
		expect(calendarBadge(undefined)).toBeNull()
	})
})

describe("leaveFormError", () => {
	it("accepts a complete form", () => {
		expect(leaveFormError(form())).toBe("")
	})
	it("needs type and dates in order", () => {
		expect(leaveFormError(form({ leave_type: "" }))).toBe("Choose a leave type.")
		expect(leaveFormError(form({ to_date: "" }))).toBe("Choose from and to dates.")
		expect(leaveFormError(form({ to_date: "2026-11-01" }))).toBe("The to date is before the from date.")
	})
	it("needs a half day inside a longer leave", () => {
		expect(leaveFormError(form({ half_day: 1 }))).toBe("Choose the half day.")
		expect(leaveFormError(form({ half_day: 1, half_day_date: "2026-11-09" }))).toBe(
			"The half day must lie within the leave."
		)
		expect(leaveFormError(form({ half_day: 1, half_day_date: "2026-11-04" }))).toBe("")
	})
	it("needs no half day date on a single day", () => {
		expect(leaveFormError(form({ to_date: "2026-11-03", half_day: 1 }))).toBe("")
	})
})

describe("leavePayload", () => {
	it("fills the half day of a one-day leave and trims the reason", () => {
		const payload = leavePayload(form({ to_date: "2026-11-03", half_day: true, description: "  dentist  " }))
		expect(payload.half_day).toBe(1)
		expect(payload.half_day_date).toBe("2026-11-03")
		expect(payload.description).toBe("dentist")
		expect(payload.cover_employee).toBeNull()
	})
	it("sends no half day date without a half day", () => {
		expect(leavePayload(form({ half_day_date: "2026-11-04" })).half_day_date).toBeNull()
	})
})
