import { describe, expect, it } from "vitest"
import { encounterCallUrl, encounterCallWindowName } from "./ophiceCall.js"

describe("encounterCallUrl", () => {
	const ON = "config.startWithAudioMuted=false&config.startWithVideoMuted=false&config.prejoinConfig.enabled=false&config.prejoinPageEnabled=false"

	it("opens the room on its Jitsi host with my name", () => {
		const url = encounterCallUrl({ domain: "meet.jit.si", room: "ophice-abc123" }, "Gunther Schmidt")
		expect(url).toBe(`https://meet.jit.si/ophice-abc123#${ON}&userInfo.displayName=%22Gunther%20Schmidt%22`)
	})

	it("starts with my mic and camera on, without the pre-join screen", () => {
		const settings = new URLSearchParams(encounterCallUrl({ domain: "meet.jit.si", room: "r" }).split("#")[1])
		expect(settings.get("config.startWithAudioMuted")).toBe("false")
		expect(settings.get("config.startWithVideoMuted")).toBe("false")
		expect(settings.get("config.prejoinConfig.enabled")).toBe("false")
	})

	it("works without a name and tidies the host", () => {
		expect(encounterCallUrl({ domain: "https://jitsi.example.com/", room: "r1" })).toBe(`https://jitsi.example.com/r1#${ON}`)
	})

	it("keeps the room inside the path", () => {
		expect(encounterCallUrl({ domain: "meet.jit.si", room: "a/b?c#d" })).toBe(`https://meet.jit.si/a%2Fb%3Fc%23d#${ON}`)
	})

	it("gives nothing without a call or with a bad host", () => {
		expect(encounterCallUrl(null)).toBe("")
		expect(encounterCallUrl({ domain: "meet.jit.si", room: "" })).toBe("")
		for (const domain of ["evil.com/x", "a@evil.com", "evil.com?x", ""]) {
			expect(encounterCallUrl({ domain, room: "r" })).toBe("")
		}
	})
})

describe("encounterCallWindowName", () => {
	it("is stable per room and safe as a window name", () => {
		expect(encounterCallWindowName({ room: "ophice-abc 1!" })).toBe("ophice-call-ophice-abc1")
	})
})
