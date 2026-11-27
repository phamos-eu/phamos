// Walking past other chips: they block a step that brings me too close, never one that takes me
// away. Two chips that already overlap (a reload onto someone's spot, both walking at the same
// moment, a chip arriving where I stand) can always walk apart again (#2160).

/**
 * True when stepping from `from` to `to` takes my chip closer to a chip it is already too close
 * to, or into one. Offline (away) chips never block.
 */
export function stepBlocked(others, from, to, minDistance) {
	return (others || []).some((o) => {
		if (o.offline) return false
		const after = Math.hypot(o.x - to.x, o.y - to.y)
		if (after >= minDistance) return false
		return after < Math.hypot(o.x - from.x, o.y - from.y)
	})
}
