import { createLatest, expiryFromNow } from "./hold_clock.js"

describe("expiryFromNow", () => {
	it("counts the minutes from the visitor's clock, whatever the server's clock says", () => {
		const visitorNow = Date.UTC(2026, 9, 24, 10, 0, 0)
		expect(expiryFromNow(20, visitorNow)).toBe(visitorNow + 20 * 60 * 1000)
	})

	it("accepts the minutes as a string", () => {
		expect(expiryFromNow("20", 0)).toBe(1200000)
	})
})

describe("createLatest", () => {
	it("drops an answer that arrives after a newer request was sent", () => {
		const latest = createLatest()
		const older = latest.next()
		const newer = latest.next()
		expect(latest.isLatest(newer)).toBe(true)
		expect(latest.isLatest(older)).toBe(false)
	})
})
