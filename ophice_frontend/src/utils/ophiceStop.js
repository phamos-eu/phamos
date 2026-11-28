// Passing by (#2171): a stop opens the chat, the call or the meeting only after a short pause.
// Tapping past someone or through a meeting space doesn't pull me in; walking on within the pause
// cancels it.

/** The pause after a stop, in ms (PM, 2026-11-27: "a slight delay"). */
export const STOP_DELAY = 800

/**
 * One pending stop at a time.
 * @param {() => void} open  what a stop does once the pause is over
 * @param {() => boolean} still  true while I still stand (no key held, not in the air, no Go to)
 */
export function stopTimer(open, still, delay = STOP_DELAY) {
	let timer = null
	function fire() {
		timer = null
		if (still()) open()
	}
	return {
		/** I stopped: open after the pause (a later stop starts the pause again). */
		stopped() {
			clearTimeout(timer)
			timer = setTimeout(fire, delay)
		},
		/** I walk on (or leave the page): nothing opens. */
		cancel() {
			clearTimeout(timer)
			timer = null
		},
		/** Open now, when a stop is pending (I started typing to the person). */
		flush() {
			if (!timer) return false
			clearTimeout(timer)
			fire()
			return true
		},
		get pending() {
			return timer !== null
		},
	}
}
