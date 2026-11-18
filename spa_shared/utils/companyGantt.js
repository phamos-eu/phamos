/**
 * Rows for the "All departments" Tasks Gantt of the General Management Cockpit (#1948).
 *
 * The backend sends one group per cockpit department (get_company_tasks). The Gantt shows them
 * as a flat list: a header row per department, then its Tasks unless the group is collapsed.
 * Kept free of Vue and the DOM so it can be unit-tested.
 */

export const GROUP_ROW_PREFIX = "group:"

export function groupRowName(department) {
	return `${GROUP_ROW_PREFIX}${department}`
}

export function isGroupRow(name) {
	return String(name || "").startsWith(GROUP_ROW_PREFIX)
}

/** Same fields as the search of the department Tasks Gantt (TasksInbox.vue). */
export function matchesSearch(task, query) {
	const q = String(query || "").trim().toLowerCase()
	if (!q) return true
	return [task.subject, task.name, task.description, task.status, task.priority, ...(task.assignee_names || [])]
		.filter(Boolean)
		.some((value) => String(value).toLowerCase().includes(q))
}

/** Earliest start and latest end of the dated Tasks (ISO dates compare as strings), or null. */
export function groupSpan(tasks) {
	let start = null
	let end = null
	for (const task of tasks || []) {
		if (!task.exp_start_date) continue
		const taskEnd = task.exp_end_date && task.exp_end_date > task.exp_start_date ? task.exp_end_date : task.exp_start_date
		if (!start || task.exp_start_date < start) start = task.exp_start_date
		if (!end || taskEnd > end) end = taskEnd
	}
	return start ? { start, end } : null
}

/**
 * Flatten the department groups into Gantt rows.
 *
 * - Header row per group: name `group:<department>`, the cockpit label as subject, the group's
 *   span as dates (its summary bar), `is_group`, `locked`, `group_count`, `collapsed`. A group
 *   without dated Tasks gets `fallbackDate` and `empty: true`, so its bar can be hidden.
 * - Task rows in the cockpit colour; `locked` unless the group is the cockpit's own.
 * - With a search, groups without a match are left out.
 * - Dependencies on Tasks that are not shown are dropped (subtasks stay in the departments).
 */
export function buildCompanyRows(groups, { collapsed = [], search = "", fallbackDate = null } = {}) {
	const collapsedSet = new Set(collapsed)
	const searching = Boolean(String(search || "").trim())
	const rows = []
	for (const group of groups || []) {
		const tasks = (group.tasks || []).filter((task) => matchesSearch(task, search))
		if (searching && !tasks.length) continue
		const span = groupSpan(tasks)
		const isCollapsed = collapsedSet.has(group.department)
		rows.push({
			name: groupRowName(group.department),
			subject: group.label,
			status: "",
			color: group.color,
			progress: 0,
			exp_start_date: span ? span.start : fallbackDate,
			exp_end_date: span ? span.end : fallbackDate,
			depends_on_tasks: "",
			department: group.department,
			is_group: true,
			locked: true,
			empty: !span,
			group_count: tasks.length,
			collapsed: isCollapsed,
		})
		if (isCollapsed) continue
		for (const task of tasks) {
			rows.push({ ...task, color: group.color, locked: !group.own, group: group.department })
		}
	}

	const shown = new Set(rows.map((row) => row.name))
	return rows.map((row) => {
		if (!row.depends_on_tasks) return row
		const kept = String(row.depends_on_tasks)
			.split(",")
			.map((name) => name.trim())
			.filter((name) => name && shown.has(name))
		return { ...row, depends_on_tasks: kept.join(",") }
	})
}
