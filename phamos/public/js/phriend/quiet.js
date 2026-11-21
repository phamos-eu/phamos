// Leave me in peace (#2010): when Phriend is quiet and when its warnings are muted. Pure
// functions over the state the server keeps per user (phamos/phriend/quiet.py):
//   { quiet_until: ms | "forever" | null, warnings_muted_until: ms | null }

export const FOREVER = "forever";
export const HOUR_MS = 60 * 60 * 1000;
export const MUTE_MINUTES = [30, 60, 90]; // 90 at most (PM, 2026-11-21)
export const WARNING = "alert"; // the red double exclamation gets through quiet mode

export function is_quiet(state, now) {
	const until = state && state.quiet_until;
	return until === FOREVER || (typeof until === "number" && until > now);
}

export function warnings_muted(state, now) {
	const until = state && state.warnings_muted_until;
	return typeof until === "number" && until > now;
}

// While quiet only the warning gets through, and not while warnings are muted.
export function may_react(name, state, now) {
	if (name === WARNING) return !warnings_muted(state, now);
	return !is_quiet(state, now);
}

// "For today": the user's local midnight.
export function end_of_today(now) {
	const d = new Date(now);
	d.setHours(24, 0, 0, 0);
	return d.getTime();
}

// When to wake up by itself: ms from now, or null (not quiet, or until woken).
export function wake_in(state, now) {
	const until = state && state.quiet_until;
	return typeof until === "number" && until > now ? until - now : null;
}
