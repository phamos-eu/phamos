/**
 * Wording for soft field locks (see useFieldLocks / phamos.api.presence).
 *
 * A lock is held while another user has the field focused. It is released
 * when they leave the field; if their tab closes or loses connection the
 * server drops it once the last heartbeat expires (at most 90 s).
 */

export function lockHolder(lock) {
	return lock?.full_name || lock?.user || "Someone"
}

/** Seconds until the lock expires on its own, or null if unknown. */
export function secondsUntilExpiry(lock, now = Date.now()) {
	if (!lock?.expiresAt) return null
	return Math.max(0, Math.ceil((lock.expiresAt - now) / 1000))
}

/** One-line headline, e.g. "Anna Muster is editing the description". */
export function lockHeadline(lock, fieldLabel = "this field") {
	return `${lockHolder(lock)} is editing ${fieldLabel}`
}

/** Why it is blocked and when it unblocks. */
export function lockExplanation(lock, now = Date.now()) {
	const seconds = secondsUntilExpiry(lock, now)
	const automatic = seconds === null ? "within 90 s" : `in ${seconds} s`
	return (
		"Read-only for you, so your edits and theirs don't overwrite each other. " +
		`Unlocks when they leave the field, or automatically ${automatic} if their window was closed.`
	)
}

/** Headline and explanation in one string, for tooltips and toasts. */
export function lockMessage(lock, fieldLabel, now = Date.now()) {
	return `${lockHeadline(lock, fieldLabel)}. ${lockExplanation(lock, now)}`
}
