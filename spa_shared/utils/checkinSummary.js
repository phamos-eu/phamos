// Check-in state as the Personal Cockpit shows it (#1571). The server sends the state with its
// own clock (`server_now`); between reloads the worked time is advanced locally once a minute.

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
	if (!h) return `${m} min`
	return m ? `${h} h ${m} min` : `${h} h`
}

// The button label and icon for the next action.
export function actionLabel(state) {
	return state?.next_action === "OUT"
		? { label: "Check out", icon: "log-out" }
		: { label: "Check in", icon: "log-in" }
}

// "in since 08:02", "out since 12:01", "in since Tue 17:40" for a check-in left open on an
// earlier day. `formatTime` and `formatDay` turn a server datetime into display text.
export function caption(state, formatTime, formatDay) {
	const last = state?.last
	if (!last) return "not checked in yet"
	const when = state.stale_in ? `${formatDay(last.time)} ${formatTime(last.time)}` : formatTime(last.time)
	return `${last.log_type === "IN" ? "in" : "out"} since ${when}`
}

// Today's logs as rows for the sidebar; the last IN without an OUT is marked as running.
export function todayRows(state) {
	const logs = state?.today?.logs || []
	return logs.map((log, index) => ({
		...log,
		running: log.log_type === "IN" && index === logs.length - 1 && state.next_action === "OUT",
	}))
}

// Ctrl/Cmd+Z outside text fields revokes a pending check-in.
export function isUndoKey(event) {
	if (!(event.ctrlKey || event.metaKey) || event.shiftKey || event.altKey) return false
	if (String(event.key).toLowerCase() !== "z") return false
	const target = event.target
	const tag = target?.tagName
	return !(tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target?.isContentEditable)
}
