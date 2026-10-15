// ToDo ordering for the Personal Cockpit (phamos/phamos#1541), mirroring the server
// (phamos.api.personal_todos.sort_key) so the list stays in order after local edits:
// due date ascending with undated last, then High, Medium, Low, then oldest first.
// Pure module (no DOM, no Vue) so it runs under Vitest in Node.

export const TODO_PRIORITIES = ["High", "Medium", "Low"]

const PRIORITY_RANK = { High: 0, Medium: 1, Low: 2 }

function rank(priority) {
	return priority in PRIORITY_RANK ? PRIORITY_RANK[priority] : TODO_PRIORITIES.length
}

export function compareTodos(a, b) {
	const aDate = a.date || ""
	const bDate = b.date || ""
	if (!aDate !== !bDate) return aDate ? -1 : 1
	if (aDate !== bDate) return aDate < bDate ? -1 : 1
	const byPriority = rank(a.priority) - rank(b.priority)
	if (byPriority) return byPriority
	const aCreated = a.creation || ""
	const bCreated = b.creation || ""
	return aCreated < bCreated ? -1 : aCreated > bCreated ? 1 : 0
}

export function sortTodos(todos) {
	return [...todos].sort(compareTodos)
}

export function todoPriorityTheme(priority) {
	if (priority === "High") return "red"
	if (priority === "Low") return "gray"
	return "orange"
}

/** Case-insensitive search over the text a user sees on a ToDo row. */
export function matchesTodo(todo, query) {
	const q = (query || "").trim().toLowerCase()
	if (!q) return true
	return [todo.summary, todo.reference_type, todo.reference_name, todo.reference_title, todo.name]
		.filter(Boolean)
		.some((value) => String(value).toLowerCase().includes(q))
}
