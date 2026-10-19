import { describe, expect, it } from "vitest"
import { classifyPath, threadIdFromHref } from "./ravenEmbed.js"

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
