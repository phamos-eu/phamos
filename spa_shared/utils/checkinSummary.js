// Check-in state as the Personal Cockpit shows it (#1571). The server sends the state with its
// own clock (`server_now`); between reloads the worked time is advanced locally once a minute.
import { __ } from "./i18n.js"

// Minutes worked today, `elapsedSeconds` after the state was loaded.
export function liveWorkedMinutes(state, elapsedSeconds = 0) {
	const base = state?.today?.worked_minutes || 0
	if (state?.next_action !== "OUT" || state?.stale_in) return base
	return base + Math.floor(Math.max(elapsedSeconds, 0) / 60)
}

export function formatWorked(minutes) {
	const total = Math.max(0, Math.round(minutes || 0))
	const h = Math.floor(total / 60)
	const m = total % 60
	if (!h) return __("{0} min", [m])
	return m ? __("{0} h {1} min", [h, m]) : __("{0} h", [h])
}

// The button label and icon for the next action.
export function actionLabel(state) {
	return state?.next_action === "OUT"
		? { label: __("Check out"), icon: "log-out" }
		: { label: __("Check in"), icon: "log-in" }
}

// "in since 08:02", "out since 12:01", "in since Tue 17:40" for a check-in left open on an
// earlier day. `formatTime` and `formatDay` turn a server datetime into display text.
export function caption(state, formatTime, formatDay) {
	const last = state?.last
	if (!last) return __("not checked in yet")
	// The day is shown whenever the last log is not one of today's (e.g. a Thursday check-out seen
	// on Saturday), not only for a check-in left open.
	const fromToday = !state.stale_in && (state.today?.logs || []).some((log) => log.name === last.name)
	const when = fromToday ? formatTime(last.time) : `${formatDay(last.time)} ${formatTime(last.time)}`
	return last.log_type === "IN" ? __("in since {0}", [when]) : __("out since {0}", [when])
}

// Ctrl/Cmd+Z outside text fields revokes a pending check-in.
export function isUndoKey(event) {
	if (!(event.ctrlKey || event.metaKey) || event.shiftKey || event.altKey) return false
	if (String(event.key).toLowerCase() !== "z") return false
	const target = event.target
	const tag = target?.tagName
	return !(tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target?.isContentEditable)
}

// Minutes between IN and OUT pairs of one day's logs (in time order); an open IN counts until
// `now` (a Date) and not at all without it. Mirrors personal_checkin.worked_minutes.
export function worked(logs, now = null) {
	let total = 0
	let openIn = null
	const toDate = (value) => new Date(String(value).replace(" ", "T"))
	for (const log of logs) {
		if (log.log_type === "IN" && openIn === null) openIn = toDate(log.time)
		else if (log.log_type === "OUT" && openIn !== null) {
			total += Math.max(toDate(log.time) - openIn, 0)
			openIn = null
		}
	}
	if (openIn !== null && now) total += Math.max(now - openIn, 0)
	return Math.floor(total / 60000)
}
