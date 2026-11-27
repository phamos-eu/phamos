import { describe, expect, it } from "vitest"
import { browserFamily, MAX_SHOWS, readState, shouldShowHint, storageKey, writeState } from "./installHint.js"

const UA = {
	chrome:
		"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
	edge: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
	safari:
		"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
	firefox: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
}

function memoryStorage() {
	const data = {}
	return { getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => (data[k] = String(v)) }
}

const blocked = {
	getItem() {
		throw new Error("SecurityError")
	},
	setItem() {
		throw new Error("QuotaExceededError")
	},
}

describe("install hint: browser", () => {
	it("tells the browsers apart by their user agent", () => {
		expect(browserFamily(UA.chrome)).toBe("chrome")
		expect(browserFamily(UA.edge)).toBe("edge")
		expect(browserFamily(UA.safari)).toBe("safari")
		expect(browserFamily(UA.firefox)).toBe("firefox")
		expect(browserFamily("curl/8.0")).toBe("other")
	})

	it("prefers the client hints where Chromium has them", () => {
		const edge = [{ brand: "Microsoft Edge" }, { brand: "Chromium" }]
		expect(browserFamily(UA.chrome, edge)).toBe("edge")
		expect(browserFamily("", [{ brand: "Google Chrome" }, { brand: "Chromium" }])).toBe("chrome")
	})
})

describe("install hint: when it shows", () => {
	const fresh = { shown: 0, dismissed: false }

	it("shows on a first visit on a desktop browser", () => {
		expect(shouldShowHint({ installed: false, width: 1440, state: fresh })).toBe(true)
	})

	it("never shows inside the installed app or on a phone", () => {
		expect(shouldShowHint({ installed: true, width: 1440, state: fresh })).toBe(false)
		expect(shouldShowHint({ installed: false, width: 390, state: fresh })).toBe(false)
	})

	it("doesn't open by itself in Firefox, which can't install web apps", () => {
		expect(shouldShowHint({ installed: false, width: 1440, state: fresh, family: "firefox" })).toBe(false)
		expect(shouldShowHint({ installed: false, width: 1440, state: fresh, family: "safari" })).toBe(true)
	})

	it("stays away after “Don't show again” and after the last “Later”", () => {
		expect(shouldShowHint({ installed: false, width: 1440, state: { shown: 1, dismissed: true } })).toBe(false)
		expect(shouldShowHint({ installed: false, width: 1440, state: { shown: MAX_SHOWS - 1, dismissed: false } })).toBe(true)
		expect(shouldShowHint({ installed: false, width: 1440, state: { shown: MAX_SHOWS, dismissed: false } })).toBe(false)
	})

	it("remembers per cockpit", () => {
		const storage = memoryStorage()
		writeState(storage, storageKey("/implementation-cockpit"), { shown: 2, dismissed: true })
		expect(readState(storage, storageKey("/implementation-cockpit"))).toEqual({ shown: 2, dismissed: true })
		expect(readState(storage, storageKey("/team-cockpit"))).toEqual({ shown: 0, dismissed: false })
	})

	it("works when the browser blocks storage", () => {
		expect(readState(blocked, "k")).toEqual({ shown: 0, dismissed: false })
		expect(readState(null, "k")).toEqual({ shown: 0, dismissed: false })
		expect(writeState(blocked, "k", { shown: 1, dismissed: false })).toBe(false)
		expect(writeState(null, "k", { shown: 1, dismissed: false })).toBe(false)
		const broken = memoryStorage()
		broken.setItem("k", "{not json")
		expect(readState(broken, "k")).toEqual({ shown: 0, dismissed: false })
	})
})
