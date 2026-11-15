// Reordering a list by dragging (#1919): where an item lands, and the list after the move.
// Pure, so it can be tested without a browser.

/**
 * The index an item dragged to pointer height `y` lands at, from the other items' boxes.
 *
 * @param {number} y the pointer's clientY
 * @param {{ top: number, height: number }[]} rects every item's box, in list order (the dragged
 *   item included)
 * @param {number} from the dragged item's index
 * @returns {number} the index it gets after the move (0 … rects.length - 1)
 */
export function dropIndex(y, rects, from) {
	let index = 0
	rects.forEach((r, i) => {
		if (i !== from && y > r.top + r.height / 2) index++
	})
	return index
}

/** The list with the item at `from` moved to `to` (a new array). */
export function moved(list, from, to) {
	const next = [...list]
	if (from < 0 || from >= next.length || to < 0 || to >= next.length) return next
	const [item] = next.splice(from, 1)
	next.splice(to, 0, item)
	return next
}

/**
 * How far each item is shifted while the item at `from` is held over slot `to`: the items it
 * passed make room by one slot (`step` = the dragged item's height plus the gap). The dragged item
 * itself follows the pointer and gets 0 here.
 *
 * @returns {number[]} one offset in px per item, in list order
 */
export function dragOffsets(count, from, to, step) {
	return Array.from({ length: count }, (_, i) => {
		if (i === from) return 0
		if (from < to && i > from && i <= to) return -step
		if (to < from && i >= to && i < from) return step
		return 0
	})
}

/** Pointer travel (px) after which a press on an item becomes a drag instead of a click. */
export const DRAG_DISTANCE = 4

/** Whether a mouse or pen press has moved far enough to start dragging. */
export function passedDragDistance(dx, dy) {
	return Math.hypot(dx, dy) >= DRAG_DISTANCE
}
