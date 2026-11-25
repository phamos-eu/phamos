// Over a cockpit (#2155): walking from the mini map out of the area I stood in when the cockpit
// opened takes me back to the map, so I see where I am going.

/** The area (any kind) under the chip's middle, or null. */
export function areaUnder(areas, chip) {
	if (!chip) return null
	const cx = chip.x + 0.5
	const cy = chip.y + 0.5
	return (areas || []).find((a) => cx >= a.x && cx < a.x + a.width && cy >= a.y && cy < a.y + a.height) || null
}

/** True once the chip is no longer in the area named `start`. No start area: never. */
export function walkedOut(start, areas, chip) {
	if (!start || !chip) return false
	return areaUnder(areas, chip)?.name !== start
}

/** A field someone types in: keys there are text, never walking. */
export function isTyping(el) {
	const tag = el?.tagName
	return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || Boolean(el?.isContentEditable)
}

/**
 * Over a cockpit: a key that walks or jumps my chip (arrows, WASD, Space), not typed into a field
 * and without a modifier. Everything else belongs to the cockpit.
 */
export function isWalkKey(event, directions) {
	if (!event || isTyping(event.target) || event.metaKey || event.ctrlKey || event.altKey) return false
	return event.code === "Space" || Boolean(directions[event.key?.toLowerCase()])
}
