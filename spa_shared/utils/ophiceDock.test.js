import { describe, expect, it } from "vitest"
import { DOCK_RECT, DOCK_SIZE, dockMessage, inOphiceFrame, isOverDock, rectInParent } from "./ophiceDock.js"

// The mini map's dock, a right sidebar in the cockpit (#2155): the frame and Ophice talk by postMessage.

describe("inOphiceFrame", () => {
	it("is true only in the frame Ophice marked", () => {
		expect(inOphiceFrame({ frameElement: { dataset: { ophiceFrame: "" } } })).toBe(true)
		expect(inOphiceFrame({ frameElement: { dataset: {} } })).toBe(false)
		// A cockpit opened on its own, not inside Ophice.
		expect(inOphiceFrame({ frameElement: null })).toBe(false)
	})

	it("is false in a frame of another site, whose frame element can't be read", () => {
		const win = {
			get frameElement() {
				throw new Error("SecurityError")
			},
		}
		expect(inOphiceFrame(win)).toBe(false)
	})
})

describe("dockMessage", () => {
	const origin = "https://erp.example.com"

	it("takes a dock message of this site", () => {
		const data = { type: DOCK_SIZE, height: 120, target: false }
		expect(dockMessage({ origin, data }, DOCK_SIZE, origin)).toBe(data)
	})

	it("ignores other sites, other types and other messages", () => {
		expect(dockMessage({ origin: "https://evil.example", data: { type: DOCK_SIZE } }, DOCK_SIZE, origin)).toBeNull()
		expect(dockMessage({ origin, data: { type: DOCK_RECT } }, DOCK_SIZE, origin)).toBeNull()
		expect(dockMessage({ origin, data: "hello" }, DOCK_SIZE, origin)).toBeNull()
		expect(dockMessage({ origin, data: null }, DOCK_SIZE, origin)).toBeNull()
	})
})

describe("rectInParent", () => {
	it("adds the frame's place to the spot's place", () => {
		const frame = { left: 0, top: 48 }
		const spot = { left: 8, top: 500, width: 192, height: 200, bottom: 700 }
		expect(rectInParent(frame, spot)).toEqual({ left: 8, top: 548, width: 192, height: 200, bottom: 748 })
	})
})

describe("isOverDock", () => {
	// The right sidebar (or its drop strip) of a 1280 px wide cockpit.
	const rect = { left: 992, top: 0, width: 288, height: 800, bottom: 800 }

	it("docks when let go over the right sidebar", () => {
		expect(isOverDock(1100, 400, rect)).toBe(true)
		// A little short of it still counts.
		expect(isOverDock(980, 400, rect)).toBe(true)
	})

	it("hovers when let go over the cockpit page", () => {
		expect(isOverDock(600, 400, rect)).toBe(false)
	})

	it("never docks without a spot", () => {
		expect(isOverDock(1100, 400, null)).toBe(false)
	})
})
