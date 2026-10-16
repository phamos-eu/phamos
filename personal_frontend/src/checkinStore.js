// My check-in state (#1571), shared by the top-bar button and the sidebar. Loaded at start and
// refreshed on `cockpit_checkin_changed`, when the tab becomes visible, and after every action.
import { reactive } from "vue"
import { call } from "frappe-ui"
import spaConfig from "./config"

export const checkin = reactive({
	state: null,
	loaded: false,
	loadedAt: 0,
	// The log just made, while it can still be revoked: { name, log_type, time, until }.
	pending: null,
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
