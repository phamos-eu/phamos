// My check-in state (#1571), shared by the top-bar button and the sidebar. Loaded at start and
// refreshed on `cockpit_checkin_changed`, when the tab becomes visible, and after every action.
import { reactive } from "vue"
import { call } from "frappe-ui"
import { formatTime } from "@spa/utils/datetime.js"
import { notify } from "@spa/utils/notify.js"
import spaConfig from "./config"

export const checkin = reactive({
	state: null,
	loaded: false,
	loadedAt: 0,
	// The log just made, while it can still be revoked: { name, log_type, time, until }.
	pending: null,
	busy: false,
})

let inflight = null

export function setCheckin(state) {
	checkin.state = state || null
	checkin.loaded = true
	checkin.loadedAt = Date.now()
}

export async function loadCheckin() {
	if (!inflight) {
		inflight = call(`${spaConfig.api}.get_checkin_state`)
			.then(setCheckin)
			.catch(() => setCheckin(null)) // no button rather than a broken one
			.finally(() => (inflight = null))
	}
	return inflight
}

// Shown at all only for a user with an active Employee who may create check-ins.
export function checkinUsable(state = checkin.state) {
	return Boolean(state?.available && state.employee && state.can_checkin)
}


function currentPosition() {
	return new Promise((resolve, reject) => {
		if (!navigator.geolocation) {
			reject(new Error("This browser cannot share its location."))
			return
		}
		navigator.geolocation.getCurrentPosition(
			(position) => resolve(position.coords),
			() => reject(new Error("Please allow location access to check in.")),
			{ enableHighAccuracy: true, timeout: 10000 }
		)
	})
}

// Check in or out now (the next action). `beforeCheckout` may cancel a check-out by resolving
// to false (the timer guard). Afterwards the log can be revoked while `checkin.pending` is set.
export async function checkInOrOut(beforeCheckout = null) {
	const state = checkin.state
	if (checkin.busy || !checkinUsable(state)) return
	const logType = state.next_action
	if (logType === "OUT" && beforeCheckout && !(await beforeCheckout())) return
	checkin.busy = true
	try {
		const args = { log_type: logType }
		if (state.geolocation_required) {
			const coords = await currentPosition()
			args.latitude = coords.latitude
			args.longitude = coords.longitude
		}
		const result = await call(`${spaConfig.api}.add_checkin`, args)
		setCheckin(result.state)
		checkin.pending = result.state.can_revoke ? { ...result.log } : null
		notify.success(`${logType === "IN" ? "Checked in" : "Checked out"} at ${formatTime(result.log.time).slice(0, 5)}`)
	} catch (e) {
		notify.error(e?.messages?.[0] || e?.message || "That did not work")
		loadCheckin()
	} finally {
		checkin.busy = false
	}
}
