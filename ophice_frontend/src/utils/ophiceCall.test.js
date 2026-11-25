import { describe, expect, it } from "vitest"
import { jitsiCallUrl, encounterCallWindowName } from "./ophiceCall.js"

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
