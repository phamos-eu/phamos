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
