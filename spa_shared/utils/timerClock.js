// Clock maths for the timesheet timer (#1572). The server sends a snapshot (elapsed work seconds,
// break start, its own `server_now`); between reloads the clock is advanced locally, and only
// while the session is running, the same way the Developer Action Panel counts.
import { secondsBetween } from "./focusRules.js"

export const MIN_EXPECTED_HOURS = 0.25

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
	if (minutes === 0) return "under a minute"
	if (minutes < 60) return `${minutes} min`
	const h = Math.floor(minutes / 60)
	const m = minutes % 60
	return m ? `${h} h ${m} min` : `${h} h`
}

// "12 min left" or "8 min over" against the expected time; empty without one.
export function budgetText(session, elapsed) {
	const expected = session?.expected_time || 0
	if (!expected) return ""
	const rest = expected - elapsed
	return rest >= 0 ? `${formatMinutes(rest)} left` : `${formatMinutes(rest)} over`
}

export function isOverBudget(session, elapsed) {
	return Boolean(session?.expected_time) && elapsed > session.expected_time
}

// Expected time is entered in hours (0.25 steps, like the Developer Action Panel).
export function hoursToSeconds(hours) {
	const value = Number(String(hours).replace(",", "."))
	if (!Number.isFinite(value) || value < MIN_EXPECTED_HOURS) return null
	return Math.round(value * 3600)
}
