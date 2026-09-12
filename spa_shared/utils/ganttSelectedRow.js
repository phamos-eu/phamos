const ROW_CLASS = "hr-gantt-selected-row"

/**
 * Full-width row highlight behind the selected task bar (grid layer, under bars).
 */
export function updateGanttSelectedRow(gantt, selectedId) {
	if (!gantt?.layers?.grid) return

	const grid = gantt.layers.grid
	grid.querySelectorAll(`.${ROW_CLASS}`).forEach((el) => el.remove())

	if (!selectedId || !gantt.bars?.length) return

	const bar = gantt.bars.find((b) => b.task?.id === selectedId)
	if (!bar) return

	const svg = gantt.$svg
	const width = Number(svg?.getAttribute("width")) || grid.getBBox?.().width || 0
	if (!width) return

	const rowHeight = (gantt.options.bar_height || 0) + (gantt.options.padding || 0)
	const y = bar.y - (gantt.options.padding || 0) / 2

	const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect")
	rect.setAttribute("x", "0")
	rect.setAttribute("y", String(Math.max(0, y)))
	rect.setAttribute("width", String(width))
	rect.setAttribute("height", String(rowHeight))
	rect.setAttribute("class", ROW_CLASS)
	rect.setAttribute("pointer-events", "none")
	grid.appendChild(rect)
}
