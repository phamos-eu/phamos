import { lockExplanation, lockHeadline, lockMessage, secondsUntilExpiry } from "./fieldLockText.js"

const lock = { user: "anna@example.com", full_name: "Anna Muster", expiresAt: 100_000 }

describe("field lock wording", () => {
	it("names the holder and the field", () => {
		expect(lockHeadline(lock, "the description")).toBe("Anna Muster is editing the description")
		expect(lockHeadline({ user: "anna@example.com" })).toBe("anna@example.com is editing this field")
	})

	it("explains why and when it unlocks, with a countdown", () => {
		const text = lockExplanation(lock, 26_000)
		expect(text).toContain("Read-only for you")
		expect(text).toContain("Unlocks when they leave the field")
		expect(text).toContain("automatically in 74 s")
	})

	it("falls back to the maximum when the expiry is unknown", () => {
		expect(lockExplanation({ full_name: "Anna" })).toContain("within 90 s")
		expect(secondsUntilExpiry(lock, 200_000)).toBe(0)
	})

	it("combines both for tooltips", () => {
		expect(lockMessage(lock, "the subject", 26_000)).toMatch(/^Anna Muster is editing the subject\. Read-only/)
	})
})
