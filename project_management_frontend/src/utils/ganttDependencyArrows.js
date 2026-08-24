const ARROW_HEAD = " m -5 -5 l 5 5 l -5 5"
const LANE_BASE = 10
const LANE_STEP = 8

/**
 * Orthogonal dependency path: exit predecessor right-mid → lane right → vertical → enter successor left-mid.
 */
export function orthogonalDependencyPath(startX, startY, endX, endY, laneIndex = 0) {
	const routeX = startX + LANE_BASE + laneIndex * LANE_STEP
	return `M ${startX} ${startY} H ${routeX} V ${endY} H ${endX}${ARROW_HEAD}`
}

function barRightMid(barEl) {
	return {
		x: barEl.getX() + barEl.getWidth(),
		y: barEl.getY() + barEl.getHeight() / 2,
	}
}

function barLeftMid(barEl) {
	return {
		x: barEl.getX(),
		y: barEl.getY() + barEl.getHeight() / 2,
	}
}

/**
 * Replace frappe-gantt curved under-bar arrows with orthogonal right-mid → left-mid routing.
 */
export function restyleDependencyArrows(gantt) {
	if (!gantt?.arrows?.length) return

	const laneByFrom = {}
	for (const arrow of gantt.arrows) {
		const fromId = arrow.from_task?.task?.id
		if (!fromId) continue
		const laneIndex = laneByFrom[fromId] || 0
		laneByFrom[fromId] = laneIndex + 1

		const fromBar = arrow.from_task?.$bar
		const toBar = arrow.to_task?.$bar
		if (!fromBar || !toBar) continue

		const start = barRightMid(fromBar)
		const end = barLeftMid(toBar)
		const path = orthogonalDependencyPath(start.x, start.y, end.x, end.y, laneIndex)

		arrow.element?.setAttribute("d", path)
		arrow.path = path
	}
}
