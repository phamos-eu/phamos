import { describe, expect, it } from "vitest"
import {
	CALL_CHAT_MIN,
	CALL_DEFAULT,
	CALL_MIN_W,
	callBox,
	callMaxHeight,
	encounterCallWindowName,
	jitsiCallUrl,
	resizeCall,
} from "./ophiceCall.js"

describe("jitsiCallUrl", () => {
	const ON = "config.startWithAudioMuted=false&config.startWithVideoMuted=false&config.prejoinConfig.enabled=false&config.prejoinPageEnabled=false"

	it("opens the room on its Jitsi host with my name", () => {
		const url = jitsiCallUrl({ domain: "meet.jit.si", room: "ophice-abc123" }, "Gunther Schmidt")
		expect(url).toBe(`https://meet.jit.si/ophice-abc123#${ON}&userInfo.displayName=%22Gunther%20Schmidt%22`)
	})

	it("starts with my mic and camera on, without the pre-join screen", () => {
		const settings = new URLSearchParams(jitsiCallUrl({ domain: "meet.jit.si", room: "r" }).split("#")[1])
		expect(settings.get("config.startWithAudioMuted")).toBe("false")
		expect(settings.get("config.startWithVideoMuted")).toBe("false")
		expect(settings.get("config.prejoinConfig.enabled")).toBe("false")
	})

	it("works without a name and tidies the host", () => {
		expect(jitsiCallUrl({ domain: "https://jitsi.example.com/", room: "r1" })).toBe(`https://jitsi.example.com/r1#${ON}`)
	})

	it("keeps the room inside the path", () => {
		expect(jitsiCallUrl({ domain: "meet.jit.si", room: "a/b?c#d" })).toBe(`https://meet.jit.si/a%2Fb%3Fc%23d#${ON}`)
	})

	it("gives nothing without a call or with a bad host", () => {
		expect(jitsiCallUrl(null)).toBe("")
		expect(jitsiCallUrl({ domain: "meet.jit.si", room: "" })).toBe("")
		for (const domain of ["evil.com/x", "a@evil.com", "evil.com?x", ""]) {
			expect(jitsiCallUrl({ domain, room: "r" })).toBe("")
		}
	})
})

describe("encounterCallWindowName", () => {
	it("is stable per room and safe as a window name", () => {
		expect(encounterCallWindowName({ room: "ophice-abc 1!" })).toBe("ophice-call-ophice-abc1")
	})
})

describe("callBox", () => {
	const big = { width: 3000, height: 2000 }

	it("keeps the old size by default: chat 288, video 768 x 432", () => {
		expect(callBox(null, big)).toMatchObject({ w: CALL_DEFAULT.w, h: CALL_DEFAULT.h, videoW: 768, videoH: 432, chatW: 288 })
	})

	it("never lets the video get taller than square, nor the chat narrower than 144", () => {
		const box = callBox({ w: 800, h: 1500 }, big)
		expect(box.videoW).toBe(box.videoH)
		expect(box.chatW).toBe(CALL_CHAT_MIN)
	})

	it("never lets the video get wider than 16:9; the chat takes the rest", () => {
		const box = callBox({ w: 2000, h: 489 }, big)
		expect(box.videoW).toBe(768)
		expect(box.chatW).toBe(2000 - 1 - 16 - 768)
	})

	it("stays inside the stage", () => {
		const box = callBox({ w: 2000, h: 1200 }, { width: 900, height: 500 })
		expect(box.w).toBeLessThanOrEqual(900)
		expect(box.h).toBeLessThanOrEqual(500)
	})
})

describe("resizeCall", () => {
	const view = { width: 1600, height: 900 }
	const from = { left: 300, top: 200, w: 1000, h: 489 }

	it("moves the left and top edges, the opposite sides stay", () => {
		const box = resizeCall(from, "nw", -100, -50, view)
		expect(box).toEqual({ left: 200, top: 150, w: 1100, h: 539 })
	})

	it("grows right and down only up to the stage's edge", () => {
		const box = resizeCall(from, "se", 900, 900, view)
		expect(box.left + box.w).toBe(1600)
		expect(box.top + box.h).toBeLessThanOrEqual(900)
	})

	it("stops at a square video when pulled taller", () => {
		const tall = { width: 1600, height: 2000 }
		const box = resizeCall(from, "s", 0, 1200, tall)
		expect(box.h).toBe(callMaxHeight(box.w))
		const shown = callBox(box, tall)
		expect(shown.videoW).toBe(shown.videoH)
	})

	it("stops at the smallest size", () => {
		const box = resizeCall(from, "e", -5000, 0, view)
		expect(box.w).toBe(CALL_MIN_W)
	})
})
