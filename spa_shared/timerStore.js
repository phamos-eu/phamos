// The user's timesheet timer (#1572), shared by the top-bar control and other parts of the
// cockpit (the check-out guard). Loaded at start, refreshed on `cockpit_timer_changed`, when
// the tab becomes visible, and after every action.
import { reactive } from "vue"
import { call } from "frappe-ui"
import spaConfig from "@/config"

export const timer = reactive({
	state: null,
	loaded: false,
	loadedAt: 0,
	// Set by requestTimerStop(): the control opens its stop dialog and resolves when done.
	stopRequest: null,
	// Bumped by requestTimerStart(): the control opens its start dialog (e.g. from a Create menu).
	startRequest: 0,
})

let inflight = null

export function setTimer(state) {
	timer.state = state || null
	timer.loaded = true
	timer.loadedAt = Date.now()
}

export async function loadTimer() {
	if (!inflight) {
		inflight = call(`${spaConfig.api}.get_timer_state`)
			.then(setTimer)
			.catch(() => setTimer(null))
			.finally(() => (inflight = null))
	}
	return inflight
}

export function activeSession(state = timer.state) {
	const session = state?.session
	return session && ["running", "paused"].includes(session.state) ? session : null
}

// Ask the top-bar control to stop the running timer. Resolves true once it is stopped and
// submitted, false when the user cancels.
export function requestTimerStop() {
	return new Promise((resolve) => {
		timer.stopRequest = { resolve }
	})
}

export function requestTimerStart() {
	timer.startRequest += 1
}
