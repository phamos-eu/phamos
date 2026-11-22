/**
 * Which cockpit I am in, for Ophice's people list (#2065): a light heartbeat while this tab is
 * visible. The server keeps only the latest one, for a minute or so, and nothing for users who
 * hide their details in Ophice.
 */
import { call } from "frappe-ui"

const EVERY_MS = 30000
let timer = null

function beat() {
	const route = window.frappe?.boot?.default_route
	if (!route || document.visibilityState !== "visible") return
	call("phamos.api.ophice.cockpit_heartbeat", { route }).catch(() => {})
}

function onVisibility() {
	if (document.visibilityState === "visible") beat()
}

/** Start once per page; returns a stop function. */
export function startCockpitPresence() {
	if (timer) return stopCockpitPresence
	beat()
	timer = setInterval(beat, EVERY_MS)
	document.addEventListener("visibilitychange", onVisibility)
	return stopCockpitPresence
}

export function stopCockpitPresence() {
	clearInterval(timer)
	timer = null
	document.removeEventListener("visibilitychange", onVisibility)
}
