import { describe, expect, it } from "vitest"
import { classifyPath, installGuard, routeFrame, threadIdFromHref } from "./ravenEmbed.js"

const CHANNEL = "/raven/Issues/issues-issue-iss-2026-00044"

describe("Raven embed paths", () => {
	it("keeps the channel and its threads in the frame", () => {
		expect(classifyPath(CHANNEL, CHANNEL)).toBe("channel")
		expect(classifyPath(`${CHANNEL}/`, CHANNEL)).toBe("channel")
		expect(classifyPath(`${CHANNEL}/thread/tlj581p2hq`, CHANNEL)).toBe("channel")
	})

	it("compares encoded and decoded paths alike", () => {
		const channel = "/raven/My%20Space/my-space-issue-1"
		expect(classifyPath("/raven/My Space/my-space-issue-1", channel)).toBe("channel")
		expect(classifyPath("/raven/My%20Space", channel)).toBe("home")
	})

	it("treats Raven's start pages as Back", () => {
		expect(classifyPath("/raven", CHANNEL)).toBe("home")
		expect(classifyPath("/raven/", CHANNEL)).toBe("home")
		expect(classifyPath("/raven/Issues", CHANNEL)).toBe("home")
	})

	it("sends other Raven pages to Raven", () => {
		expect(classifyPath("/raven/dm-channel/qca5kd95co", CHANNEL)).toBe("raven")
		expect(classifyPath("/raven/Issues/issues-other-channel", CHANNEL)).toBe("raven")
		expect(classifyPath(`${CHANNEL}-2`, CHANNEL)).toBe("raven")
		expect(classifyPath("/raven/threads", CHANNEL)).toBe("raven")
	})

	it("sends non-Raven pages out", () => {
		expect(classifyPath("/personal-cockpit/issues/list/ISS-1", CHANNEL)).toBe("outside")
		expect(classifyPath("/ravenous", CHANNEL)).toBe("outside")
		expect(classifyPath("/app/issue/ISS-1", CHANNEL)).toBe("outside")
	})
})

describe("Raven thread links", () => {
	it("reads the thread id from a pill's link", () => {
		expect(threadIdFromHref("/raven/Issues/issues-issue-iss-1/thread/tlj581p2hq")).toBe("tlj581p2hq")
		expect(threadIdFromHref("/raven/Issues/c/thread/abc?message_id=abc")).toBe("abc")
		expect(threadIdFromHref("/raven/Issues/c")).toBe("")
		expect(threadIdFromHref(null)).toBe("")
	})
})

// A frame window with just enough of History for the guard: entries, an index, popstate.
function fakeFrame(path) {
	const listeners = {}
	const win = {
		location: {},
		document: { addEventListener() {}, removeEventListener() {} },
		addEventListener: (type, fn) => (listeners[type] = [...(listeners[type] || []), fn]),
		removeEventListener: (type, fn) => (listeners[type] = (listeners[type] || []).filter((f) => f !== fn)),
		dispatchEvent: (event) => (listeners[event.type] || []).forEach((fn) => fn(event)),
		setTimeout: (fn, ms) => setTimeout(fn, ms),
		clearTimeout: (id) => clearTimeout(id),
		PopStateEvent: class {
			constructor(type, init) {
				this.type = type
				this.state = init?.state
			}
		},
	}
	const go = (url) => {
		const u = new URL(url, "http://site.test")
		Object.assign(win.location, { pathname: u.pathname, search: u.search, href: u.href, origin: u.origin })
	}
	class History {
		constructor() {
			this.entries = [{ state: { usr: null, key: "first", idx: 0 }, url: path }]
			this.index = 0
		}
		get state() {
			return this.entries[this.index].state
		}
		get length() {
			return this.entries.length
		}
		pushState(state, _title, url) {
			this.entries = this.entries.slice(0, this.index + 1)
			this.entries.push({ state, url })
			this.index += 1
			go(url)
		}
		replaceState(state, _title, url) {
			this.entries[this.index] = { state, url }
			go(url)
		}
		back() {
			if (this.index === 0) return
			this.index -= 1
			go(this.entries[this.index].url)
			queueMicrotask(() => win.dispatchEvent(new win.PopStateEvent("popstate", { state: this.state })))
		}
	}
	win.History = History
	win.history = new History()
	go(path)
	return win
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0))

describe("Raven frame guard (#1794)", () => {
	it("switches records without a new history entry", () => {
		const win = fakeFrame(CHANNEL)
		const other = "/raven/Issues/issues-issue-iss-2026-00045"
		routeFrame(win, other, { replace: true })
		expect(win.history.length).toBe(1)
		expect(win.location.pathname).toBe(other)
		expect(win.history.state.idx).toBe(0)
	})

	it("pushes threads with the router's next index", () => {
		const win = fakeFrame(CHANNEL)
		routeFrame(win, `${CHANNEL}/thread/abc`)
		expect(win.history.state.idx).toBe(1)
		expect(win.history.length).toBe(2)
	})

	it("opens nothing when Back or Forward lands on another Raven page", () => {
		const win = fakeFrame(CHANNEL)
		const left = []
		installGuard(win, CHANNEL, (kind, href) => left.push([kind, href]))
		win.History.prototype.replaceState.call(win.history, { key: "x", idx: 0 }, "", "/raven/Issues/old-channel")
		win.dispatchEvent(new win.PopStateEvent("popstate", {}))
		expect(left).toEqual([])
		expect(win.location.pathname).toBe(CHANNEL)
	})

	it("sends a pushed DM to Raven once and steps back to the channel", async () => {
		const win = fakeFrame(CHANNEL)
		const left = []
		installGuard(win, CHANNEL, (kind) => left.push(kind))
		win.history.pushState({ key: "dm", idx: 1 }, "", "/raven/dm-channel/abc")
		await settle()
		expect(left).toEqual(["raven"])
		expect(win.location.pathname).toBe(CHANNEL)
		expect(win.history.index).toBe(0)
	})

	it("opens one window when Raven moves twice before getting back", async () => {
		const win = fakeFrame(CHANNEL)
		const left = []
		installGuard(win, CHANNEL, (kind) => left.push(kind))
		win.history.pushState({ key: "dm", idx: 1 }, "", "/raven/dm-channel/abc")
		win.history.replaceState({ key: "dm2", idx: 1 }, "", "/raven/dm-channel/abc?x=1")
		await settle()
		expect(left).toEqual(["raven"])
	})

	it("closes the chat when Back reaches Raven's start page", () => {
		const win = fakeFrame(CHANNEL)
		const left = []
		installGuard(win, CHANNEL, (kind) => left.push(kind))
		win.History.prototype.replaceState.call(win.history, { key: "h", idx: 0 }, "", "/raven/Issues")
		win.dispatchEvent(new win.PopStateEvent("popstate", {}))
		expect(left).toEqual(["home"])
	})

	it("keeps the channel's own threads in the frame", () => {
		const win = fakeFrame(CHANNEL)
		const left = []
		const threads = []
		installGuard(win, CHANNEL, (kind) => left.push(kind), (id) => threads.push(id))
		win.history.pushState({ key: "t", idx: 1 }, "", `${CHANNEL}/thread/tlj581p2hq`)
		expect(left).toEqual([])
		expect(threads).toEqual(["tlj581p2hq"])
	})
})
