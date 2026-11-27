import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
	CALL_START_KEY,
	CALL_START_MODES,
	DEFAULT_CALL_START,
	nextCallStart,
	readCallStart,
	saveCallStart,
	CALL_CHAT_MIN,
	CALL_DEFAULT,
	CALL_HEADER,
	CALL_MIN_W,
	JITSI_TOOLBAR_BUTTONS,
	callBox,
	callMaxHeight,
	splitCall,
	encounterCallWindowName,
	jitsiCallUrl,
	nextQualityLevel,
	qualityLevel,
	qualitySync,
	resizeCall,
} from "./ophiceCall.js"

describe("JITSI_TOOLBAR_BUTTONS", () => {
	it("always has screen sharing next to mic, camera and hang-up", () => {
		expect(JITSI_TOOLBAR_BUTTONS).toEqual(expect.arrayContaining(["microphone", "camera", "desktop", "hangup"]))
	})

	it("leaves Jitsi's performance settings out: our own quality button does that", () => {
		expect(JITSI_TOOLBAR_BUTTONS).not.toContain("videoquality")
	})
})

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
		expect(settings.get("config.prejoinPageEnabled")).toBe("false")
	})

	it("starts with both off, on Jitsi's pre-join screen only when asking (#2168)", () => {
		const get = (start) => new URLSearchParams(jitsiCallUrl({ domain: "meet.jit.si", room: "r" }, "", start).split("#")[1])
		for (const [start, prejoin] of [["off", "false"], ["ask", "true"]]) {
			const settings = get(start)
			expect(settings.get("config.startWithAudioMuted")).toBe("true")
			expect(settings.get("config.startWithVideoMuted")).toBe("true")
			expect(settings.get("config.prejoinConfig.enabled")).toBe(prejoin)
			expect(settings.get("config.prejoinPageEnabled")).toBe(prejoin)
		}
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

describe("call start choice (#2168)", () => {
	const store = (initial = {}) => {
		const data = { ...initial }
		return { getItem: (k) => data[k] ?? null, setItem: (k, v) => (data[k] = v), data }
	}

	it("asks by default, and when the stored value is unknown or the storage throws", () => {
		expect(DEFAULT_CALL_START).toBe("ask")
		expect(readCallStart(store())).toBe("ask")
		expect(readCallStart(store({ [CALL_START_KEY]: "loud" }))).toBe("ask")
		expect(readCallStart(null)).toBe("ask")
		expect(readCallStart({ getItem: () => { throw new Error("blocked") } })).toBe("ask")
	})

	it("keeps the choice and steps ask → off → on → ask", () => {
		const s = store()
		saveCallStart(s, "off")
		expect(readCallStart(s)).toBe("off")
		expect(() => saveCallStart({ setItem: () => { throw new Error("full") } }, "on")).not.toThrow()
		expect(CALL_START_MODES.map(nextCallStart)).toEqual(["off", "on", "ask"])
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
		const box = callBox({ w: 2000, h: CALL_DEFAULT.h }, big)
		expect(box.videoW).toBe(768)
		expect(box.chatW).toBe(2000 - 1 - 16 - 768)
	})

	it("has room for the top bar above the video (#2135)", () => {
		const box = callBox(null, big)
		expect(box.h - box.videoH).toBe(CALL_HEADER + 16)
	})

	it("a wider chat narrows the video, but not below 1:1 (#2135)", () => {
		const box = callBox({ w: CALL_DEFAULT.w, h: CALL_DEFAULT.h, chat: 400 }, big)
		expect(box.chatW).toBe(400)
		expect(box.videoW).toBe(CALL_DEFAULT.w - 17 - 400)
		const most = callBox({ w: CALL_DEFAULT.w, h: CALL_DEFAULT.h, chat: 900 }, big)
		expect(most.videoW).toBe(432) // square
		expect(most.chatW).toBe(CALL_DEFAULT.w - 17 - 432)
	})

	it("a narrower chat than the 16:9 video leaves stays at what is left", () => {
		const box = callBox({ w: CALL_DEFAULT.w, h: CALL_DEFAULT.h, chat: 150 }, big)
		expect(box.videoW).toBe(768)
		expect(box.chatW).toBe(288)
	})

	it("stays inside the stage", () => {
		const box = callBox({ w: 2000, h: 1200 }, { width: 900, height: 500 })
		expect(box.w).toBeLessThanOrEqual(900)
		expect(box.h).toBeLessThanOrEqual(500)
	})
})

describe("splitCall", () => {
	const big = { width: 3000, height: 2000 }
	const size = { w: CALL_DEFAULT.w, h: CALL_DEFAULT.h }

	it("moves the line between chat and video", () => {
		expect(splitCall(size, 288, -50, big)).toBe(288) // the video is already 16:9
		expect(splitCall(size, 288, 100, big)).toBe(388)
	})

	it("stores the 1:1 limit, not the overshoot", () => {
		expect(splitCall(size, 288, 2000, big)).toBe(CALL_DEFAULT.w - 17 - 432)
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

describe("video quality", () => {
	it("maps Jitsi values to our levels", () => {
		expect(qualityLevel(2160)).toBe(720)
		expect(qualityLevel(1080)).toBe(720)
		expect(qualityLevel(360)).toBe(360)
		expect(qualityLevel(0)).toBe(180)
	})

	it("steps up and wraps around", () => {
		expect(nextQualityLevel(180)).toBe(360)
		expect(nextQualityLevel(360)).toBe(720)
		expect(nextQualityLevel(720)).toBe(180)
		expect(nextQualityLevel(2160)).toBe(180)
	})

	describe("qualitySync", () => {
		beforeEach(() => vi.useFakeTimers())
		afterEach(() => vi.useRealTimers())

		function setup() {
			const sent = []
			const shown = []
			const sync = qualitySync((h) => sent.push(h), (h) => shown.push(h))
			return { sent, shown, sync }
		}

		it("resends 180 until Jitsi confirms it, ignoring Jitsi's own start value", () => {
			const { sent, shown, sync } = setup()
			sync.reported(2160)
			sync.start()
			vi.advanceTimersByTime(1500)
			expect(sent).toEqual([180, 180])
			sync.reported(180)
			vi.advanceTimersByTime(10000)
			expect(sent).toEqual([180, 180])
			expect(shown).toEqual([180])
			// From now on Jitsi's toolbar counts.
			sync.reported(720)
			expect(shown).toEqual([180, 720])
		})

		it("gives up after five tries and shows what Jitsi runs at", () => {
			const { sent, shown, sync } = setup()
			sync.start()
			sync.reported(2160)
			vi.advanceTimersByTime(10000)
			expect(sent).toEqual([180, 180, 180, 180, 180])
			expect(shown).toEqual([2160])
			sync.reported(360)
			expect(shown).toEqual([2160, 360])
		})

		it("a click stops the retries and sends the chosen level", () => {
			const { sent, shown, sync } = setup()
			sync.start()
			sync.choose(360)
			vi.advanceTimersByTime(10000)
			expect(sent).toEqual([180, 360])
			expect(shown).toEqual([360])
		})
	})
})
