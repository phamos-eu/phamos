const STRIP_CLASS = "hr-gantt-today-strip-svg"
const EDGE_CLASS = "hr-gantt-today-strip-edge"
const EDGE_WIDTH = 2

/**
 * Draw today column inside the SVG grid layer (above row lines, below bars/arrows).
 * Edge line is placed at stripRect.edgeLeft (time-of-day within the day column).
 */
export function updateGanttTodayStrip(gantt, stripRect, minHeight = 0) {
	if (!gantt?.layers?.grid) return

	const grid = gantt.layers.grid
	grid.querySelectorAll(`.${STRIP_CLASS}, .${EDGE_CLASS}`).forEach((el) => el.remove())

	if (!stripRect) return

	const svg = gantt.$svg
	if (!svg) return

	const svgHeight = Number(svg.getAttribute("height")) || 0
	const height = Math.max(svgHeight, minHeight)

	const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect")
	rect.setAttribute("x", String(stripRect.left))
	rect.setAttribute("y", "0")
	rect.setAttribute("width", String(stripRect.width))
	rect.setAttribute("height", String(height))
	rect.setAttribute("class", STRIP_CLASS)
	grid.appendChild(rect)

	const edgeX = Math.max(
		stripRect.left,
		Math.min(stripRect.left + stripRect.width - EDGE_WIDTH, (stripRect.edgeLeft ?? stripRect.left) - EDGE_WIDTH / 2)
	)
	const edge = document.createElementNS("http://www.w3.org/2000/svg", "rect")
	edge.setAttribute("x", String(edgeX))
	edge.setAttribute("y", "0")
	edge.setAttribute("width", String(EDGE_WIDTH))
	edge.setAttribute("height", String(height))
	edge.setAttribute("class", EDGE_CLASS)
	grid.appendChild(edge)
}
