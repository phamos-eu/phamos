// Drag-to-link on the task Gantt (#2001, slice 2 of #1999): which bar may take a dependency.

/**
 * The bar a dragged handle may be dropped on, or null.
 *
 * @param {string} fromId the Task the drag started on (the predecessor)
 * @param {string|null} targetId the Task under the pointer
 * @param {object} rows
 * @param {(id: string) => boolean} rows.isLocked read-only or group rows
 * @param {(id: string) => string[]} rows.dependsOn the predecessors of a Task
 * @returns {string|null} targetId when the drop would add a new, non-circular link
 */
export function linkTargetId(fromId, targetId, { isLocked, dependsOn }) {
	if (!fromId || !targetId || fromId === targetId) return null
	if (isLocked(targetId)) return null
	// Already linked this way: nothing to add.
	if (dependsOn(targetId).includes(fromId)) return null
	// The direct reverse would be a loop; ERPNext refuses longer ones on save.
	if (dependsOn(fromId).includes(targetId)) return null
	return targetId
}

/**
 * Where the drag handle sits: just past the right end of the bar, vertically centred.
 * Coordinates are relative to `origin` (the chart's scrolling content box).
 *
 * @param {DOMRect} barRect
 * @param {DOMRect} originRect
 * @param {number} gap pixels between the bar's end and the handle's centre
 */
export function handlePoint(barRect, originRect, gap = 9) {
	return {
		x: barRect.right - originRect.left + gap,
		y: barRect.top - originRect.top + barRect.height / 2,
	}
}
