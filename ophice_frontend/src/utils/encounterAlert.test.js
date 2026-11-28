import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ALERT_MUTED_KEY, BLINK_MS, bellState, createEncounterAlert } from "./encounterAlert.js"

function fakeStorage() {
	const data = {}
	return {
		getItem: (k) => (k in data ? data[k] : null),
		setItem: (k, v) => (data[k] = String(v)),
		removeItem: (k) => delete data[k],
		data,
	}
}

function fakeDoc({ hidden = false, focus = true } = {}) {
	const listeners = {}
	return {
		title: "Ophice",
		hidden,
		focus,
		hasFocus() {
			return this.focus
		},
		addEventListener: (e, f) => ((listeners[e] = listeners[e] || []).push(f)),
		removeEventListener: (e, f) => (listeners[e] = (listeners[e] || []).filter((g) => g !== f)),
		fire: (e) => (listeners[e] || []).forEach((f) => f()),
		listeners,
	}
}

function fakeNotify(permission) {
	const shown = []
	function Notify(title, options) {
		this.title = title
		this.options = options
		this.close = vi.fn()
		shown.push(this)
	}
	Notify.permission = permission
	Notify.requestPermission = vi.fn(async () => (Notify.permission = "granted"))
	Notify.shown = shown
	return Notify
}

function fakeAudio() {
	const tones = []
	class Audio {
		constructor() {
			this.state = Audio.startState
			this.currentTime = 0
			this.destination = {}
			this.sampleRate = 8000
		}
		resume() {
			return Promise.reject(new Error("needs a gesture"))
		}
		createOscillator() {
			const osc = {
				frequency: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
				connect: (g) => g,
				start: vi.fn(),
				stop: vi.fn(),
			}
			tones.push(osc)
			return osc
		}
		createGain() {
			return {
				gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
				connect: (d) => d,
			}
		}
		createBuffer(channels, length) {
			const data = new Float32Array(length)
			return { getChannelData: () => data }
		}
		createBufferSource() {
			const source = { connect: (f) => f, start: vi.fn(), stop: vi.fn() }
			Audio.noises.push(source)
			return source
		}
		createBiquadFilter() {
			return { frequency: {}, Q: {}, connect: (g) => g }
		}
		close() {}
	}
	Audio.noises = []
	Audio.tones = tones
	Audio.startState = "running"
	return Audio
}

function setup({ hidden = false, focus = true, permission = "granted" } = {}) {
	const doc = fakeDoc({ hidden, focus })
	const win = { setInterval, clearInterval, focus: vi.fn() }
	const storage = fakeStorage()
	const Notify = fakeNotify(permission)
	const Audio = fakeAudio()
	const alert = createEncounterAlert({ win, doc, storage, Notify, Audio })
	return { alert, doc, win, storage, Notify, Audio }
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe("bellState", () => {
	it("is muted first, then follows the browser permission", () => {
		expect(bellState(true, "granted")).toBe("muted")
		expect(bellState(false, "default")).toBe("ask")
		expect(bellState(false, "granted")).toBe("on")
		expect(bellState(false, "denied")).toBe("blocked")
		expect(bellState(false, "unsupported")).toBe("blocked")
	})
})

describe("createEncounterAlert", () => {
	it("skips the chime while the sound is still locked, and still notifies", async () => {
		const { alert, Notify, Audio } = setup({ hidden: true })
		Audio.startState = "suspended"
		expect(alert.notify("Anna wants to chat")).toBe(true)
		await Promise.resolve() // the refused resume() must not end up unhandled
		expect(Audio.tones).toHaveLength(0)
		expect(Notify.shown).toHaveLength(1)
	})

	it("keeps the sound when resume() returns no promise (older Safari)", () => {
		const { alert, Audio } = setup()
		Audio.startState = "suspended"
		Audio.prototype.resume = function () {
			this.state = "running"
		}
		alert.unlock()
		alert.notify("Anna wants to chat")
		expect(Audio.tones).toHaveLength(2)
	})

	it("chimes while I look at the page, without title or notification", () => {
		const { alert, doc, Notify, Audio } = setup()
		expect(alert.notify("Anna wants to chat")).toBe(true)
		expect(Audio.tones).toHaveLength(2)
		expect(doc.title).toBe("Ophice")
		expect(Notify.shown).toHaveLength(0)
	})

	it("blinks the title and notifies while the tab is hidden, until it is visible again", () => {
		const { alert, doc, Notify } = setup({ hidden: true, focus: false })
		alert.notify("Anna wants to chat")
		expect(doc.title).toBe("👋 Anna wants to chat")
		vi.advanceTimersByTime(BLINK_MS)
		expect(doc.title).toBe("Ophice")
		vi.advanceTimersByTime(BLINK_MS)
		expect(doc.title).toBe("👋 Anna wants to chat")
		expect(Notify.shown).toHaveLength(1)
		expect(Notify.shown[0].title).toBe("Anna wants to chat")

		doc.hidden = false
		doc.fire("visibilitychange")
		expect(doc.title).toBe("Ophice")
		vi.advanceTimersByTime(BLINK_MS * 3)
		expect(doc.title).toBe("Ophice")
		expect(doc.listeners.visibilitychange).toHaveLength(0)
	})

	it("notifies, without blinking, when the tab is visible but another window has the focus", () => {
		const { alert, doc, Notify } = setup({ focus: false })
		alert.notify("Anna wants to chat")
		expect(Notify.shown).toHaveLength(1)
		expect(doc.title).toBe("Ophice")
	})

	it("a click on the notification brings Ophice to the front", () => {
		const { alert, win, Notify } = setup({ hidden: true, focus: false })
		alert.notify("Anna wants to chat")
		Notify.shown[0].onclick()
		expect(win.focus).toHaveBeenCalled()
		expect(Notify.shown[0].close).toHaveBeenCalled()
	})

	it("only chimes and blinks without the browser permission", () => {
		for (const permission of ["default", "denied"]) {
			const { alert, doc, Notify, Audio } = setup({ hidden: true, focus: false, permission })
			alert.notify("Anna wants to chat")
			expect(Notify.shown).toHaveLength(0)
			expect(Audio.tones).toHaveLength(2)
			expect(doc.title).toBe("👋 Anna wants to chat")
		}
	})

	it("does nothing when muted, and remembers that in the browser", () => {
		const { alert, doc, storage, Notify, Audio } = setup({ hidden: true, focus: false })
		alert.setMuted(true)
		expect(storage.data[ALERT_MUTED_KEY]).toBe("1")
		expect(alert.notify("Anna wants to chat")).toBe(false)
		expect(Audio.tones).toHaveLength(0)
		expect(Notify.shown).toHaveLength(0)
		expect(doc.title).toBe("Ophice")

		const again = createEncounterAlert({ win: { setInterval, clearInterval }, doc, storage, Notify })
		expect(again.isMuted()).toBe(true)
		alert.setMuted(false)
		expect(again.isMuted()).toBe(false)
	})

	it("muting stops a running blink and restores the title", () => {
		const { alert, doc } = setup({ hidden: true, focus: false })
		alert.notify("Anna wants to chat")
		alert.setMuted(true)
		expect(doc.title).toBe("Ophice")
	})

	it("a second encounter while blinking keeps the original title", () => {
		const { alert, doc } = setup({ hidden: true, focus: false })
		alert.notify("Anna wants to chat")
		alert.notify("Ben wants to chat")
		expect(doc.title).toBe("👋 Ben wants to chat")
		alert.stop()
		expect(doc.title).toBe("Ophice")
	})

	it("asks for the permission only once", async () => {
		const { alert, Notify } = setup({ permission: "default" })
		expect(await alert.requestPermission()).toBe("granted")
		expect(await alert.requestPermission()).toBe("granted")
		expect(Notify.requestPermission).toHaveBeenCalledTimes(1)
	})

	it("works without notifications, sound or storage", () => {
		const doc = fakeDoc({ hidden: true, focus: false })
		const alert = createEncounterAlert({ win: { setInterval, clearInterval }, doc })
		expect(alert.permission()).toBe("unsupported")
		expect(alert.notify("Anna wants to chat")).toBe(true)
		expect(doc.title).toBe("👋 Anna wants to chat")
		alert.stop()
	})
})

describe("thump (#2130)", () => {
	it("plays a falling low tone and a little soil noise", () => {
		const { alert, Audio } = setup()
		expect(alert.thump()).toBe(true)
		expect(Audio.tones).toHaveLength(1)
		expect(Audio.tones[0].frequency.setValueAtTime).toHaveBeenCalledWith(110, expect.any(Number))
		expect(Audio.tones[0].frequency.exponentialRampToValueAtTime).toHaveBeenCalledWith(55, expect.any(Number))
		expect(Audio.noises).toHaveLength(1)
	})

	it("is silent while the bell is muted", () => {
		const { alert, Audio } = setup()
		alert.setMuted(true)
		expect(alert.thump()).toBe(false)
		expect(Audio.tones).toHaveLength(0)
	})

	it("needs no sound at all", () => {
		const alert = createEncounterAlert({ win: { setInterval, clearInterval }, doc: fakeDoc() })
		expect(alert.thump()).toBe(false)
	})
})
