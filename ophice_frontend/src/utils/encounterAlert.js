// Someone started a chat with me (#2135): a chime, a blinking tab title while the tab is hidden, and
// a browser notification while I look elsewhere. Muting is per browser, not per user.

export const ALERT_MUTED_KEY = "phamos-ophice-encounter-alert-muted"
export const BLINK_MS = 1000
const NOTIFICATION_TAG = "ophice-encounter"

/** The bell's state: "muted", "ask" (permission not asked yet), "on", or "blocked" (no browser notifications). */
export function bellState(muted, permission) {
	if (muted) return "muted"
	if (permission === "default") return "ask"
	return permission === "granted" ? "on" : "blocked"
}

/**
 * The browser bits come in from outside, so tests can pass fakes:
 * `win` (window), `doc` (document), `storage` (localStorage), `Notify` (Notification), `Audio` (AudioContext).
 */
export function createEncounterAlert({ win, doc, storage, Notify, Audio } = {}) {
	let audio = null
	let blink = null

	function read() {
		try {
			return storage?.getItem(ALERT_MUTED_KEY) === "1"
		} catch {
			return false
		}
	}

	function isMuted() {
		return read()
	}

	function setMuted(muted) {
		try {
			if (muted) storage?.setItem(ALERT_MUTED_KEY, "1")
			else storage?.removeItem(ALERT_MUTED_KEY)
		} catch {
			// Private window or blocked storage: the bell still works until the reload.
		}
		if (muted) stopBlink()
	}

	function permission() {
		return Notify ? Notify.permission : "unsupported"
	}

	async function requestPermission() {
		if (!Notify || Notify.permission !== "default") return permission()
		try {
			return await Notify.requestPermission()
		} catch {
			return permission()
		}
	}

	/** Browsers only play sound after a key press or click on the page: call this from one. */
	function unlock() {
		if (!Audio) return
		try {
			audio = audio || new Audio()
			if (audio.state === "suspended") audio.resume()
		} catch {
			audio = null
		}
	}

	function chime() {
		unlock()
		if (!audio) return
		try {
			const start = audio.currentTime
			// Two soft rising tones.
			;[
				[880, 0],
				[1318.5, 0.14],
			].forEach(([frequency, offset]) => {
				const osc = audio.createOscillator()
				const gain = audio.createGain()
				osc.type = "sine"
				osc.frequency.value = frequency
				const t = start + offset
				gain.gain.setValueAtTime(0.0001, t)
				gain.gain.exponentialRampToValueAtTime(0.2, t + 0.02)
				gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.35)
				osc.connect(gain).connect(audio.destination)
				osc.start(t)
				osc.stop(t + 0.4)
			})
		} catch {
			// No sound is no reason to lose the chat.
		}
	}

	function stopBlink() {
		if (!blink) return
		win.clearInterval(blink.timer)
		doc.removeEventListener("visibilitychange", blink.onVisible)
		doc.title = blink.title
		blink = null
	}

	function startBlink(text) {
		stopBlink()
		const title = doc.title
		let on = false
		const onVisible = () => {
			if (!doc.hidden) stopBlink()
		}
		const timer = win.setInterval(() => {
			on = !on
			doc.title = on ? text : title
		}, BLINK_MS)
		blink = { title, timer, onVisible }
		doc.title = text
		on = true
		doc.addEventListener("visibilitychange", onVisible)
	}

	function showNotification(text, icon) {
		if (permission() !== "granted") return null
		try {
			const note = new Notify(text, { body: "Ophice", tag: NOTIFICATION_TAG, icon })
			note.onclick = () => {
				win.focus()
				note.close()
			}
			return note
		} catch {
			// Some browsers (Android Chrome) only allow notifications from a service worker.
			return null
		}
	}

	/** Someone started a chat with me. `text` is already translated, e.g. "Anna wants to chat". */
	function notify(text, { icon } = {}) {
		if (isMuted()) return false
		chime()
		const away = doc.hidden || !doc.hasFocus()
		if (doc.hidden) startBlink(`👋 ${text}`)
		if (away) showNotification(text, icon)
		return true
	}

	function stop() {
		stopBlink()
		try {
			audio?.close()
		} catch {
			// Already closed.
		}
		audio = null
	}

	return { isMuted, setMuted, permission, requestPermission, unlock, notify, stop }
}
