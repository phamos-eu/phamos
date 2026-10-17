// Clock maths for the timesheet timer (#1572). The server sends a snapshot (elapsed work seconds,
// break start, its own `server_now`); between reloads the clock is advanced locally, and only
// while the session is running, the same way the Developer Action Panel counts.
import { secondsBetween } from "./focusRules.js"
import { __ } from "./i18n.js"

export const MIN_EXPECTED_MINUTES = 15
export const MIN_BREAK_MINUTES = 1

export function liveElapsed(session, secondsSinceLoad = 0) {
	if (!session) return 0
	const base = session.elapsed_seconds || 0
	return session.state === "running" ? base + Math.max(0, Math.floor(secondsSinceLoad)) : base
}

// Seconds the current break has lasted, from the server's view of now.
export function liveBreak(session, serverNow, secondsSinceLoad = 0) {
	if (!session?.break_from || session.state !== "paused") return 0
	return Math.max(0, secondsBetween(session.break_from, serverNow) + Math.floor(secondsSinceLoad))
}

export function formatClock(seconds) {
	const total = Math.max(0, Math.floor(seconds || 0))
	const pad = (n) => String(n).padStart(2, "0")
	return `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`
}

export function formatMinutes(seconds) {
	const minutes = Math.round(Math.abs(seconds) / 60)
	if (minutes === 0) return __("under a minute")
	if (minutes < 60) return __("{0} min", [minutes])
	const h = Math.floor(minutes / 60)
	const m = minutes % 60
	return m ? __("{0} h {1} min", [h, m]) : __("{0} h", [h])
}

// "12 min left" or "8 min over" against the expected time; empty without one.
export function budgetText(session, elapsed) {
	const expected = session?.expected_time || 0
	if (!expected) return ""
	const rest = expected - elapsed
	return rest >= 0 ? __("{0} left", [formatMinutes(rest)]) : __("{0} over", [formatMinutes(rest)])
}

export function isOverBudget(session, elapsed) {
	return Boolean(session?.expected_time) && elapsed > session.expected_time
}

// Expected time is entered in minutes.
export function minutesToSeconds(minutes, min = MIN_EXPECTED_MINUTES) {
	const value = Number(String(minutes).replace(",", "."))
	if (!Number.isFinite(value) || value < min) return null
	return Math.round(value * 60)
}

// The clock counts down from the target: { text: "00:42:13", over: false } and once the target
// is passed { text: "+00:05:12", over: true }. Without a target it counts up.
export function countdown(targetSeconds, elapsedSeconds) {
	if (!targetSeconds) return { text: formatClock(elapsedSeconds), over: false }
	const rest = targetSeconds - elapsedSeconds
	return rest >= 0 ? { text: formatClock(rest), over: false } : { text: `+${formatClock(-rest)}`, over: true }
}
