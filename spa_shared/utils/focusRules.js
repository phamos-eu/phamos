// Focus mode rules for the Personal Cockpit (#1556). Times come from the server as naive
// "YYYY-MM-DD HH:MM:SS" strings in the same zone, so differences are safe to compute here.

export function parseServerTime(value) {
	if (!value) return null
	const date = new Date(String(value).replace(" ", "T"))
	return Number.isNaN(date.getTime()) ? null : date
}

// Seconds between two server timestamps (b - a).
export function secondsBetween(a, b) {
	const start = parseServerTime(a)
	const end = parseServerTime(b)
	if (!start || !end) return 0
	return Math.round((end.getTime() - start.getTime()) / 1000)
}

// Clock state of a session `localElapsed` seconds after it was loaded.
export function sessionClock(session, localElapsed = 0) {
	if (!session) return null
	const elapsed = secondsBetween(session.started_at, session.server_now) + localElapsed
	if (!session.planned_minutes) return { mode: "stopwatch", elapsed, remaining: null, overtime: false }
	const remaining = secondsBetween(session.server_now, session.planned_end) - localElapsed
	return { mode: "timer", elapsed, remaining: Math.max(remaining, 0), overtime: remaining < 0 }
}

export function formatClock(seconds) {
	const total = Math.max(0, Math.floor(seconds || 0))
	const h = Math.floor(total / 3600)
	const m = Math.floor((total % 3600) / 60)
	const s = total % 60
	const mm = String(m).padStart(h ? 2 : 1, "0")
	const ss = String(s).padStart(2, "0")
	return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

// How long the break-out button waits: free in the first minute, then the server's wait
// (10 s, doubling with each break-out today).
export function breakOutWait(elapsedSeconds, session) {
	if (!session) return 0
	if (elapsedSeconds < (session.free_exit_seconds ?? 60)) return 0
	return session.break_out_wait_seconds ?? 10
}

// The ToDo to show: the current one, else the first that is neither done nor parked.
export function activeItem(session) {
	const items = session?.items || []
	return items.find((item) => item.current) || items.find((item) => !item.done && !item.parked) || null
}
