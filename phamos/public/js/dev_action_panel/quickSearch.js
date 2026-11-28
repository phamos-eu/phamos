// Quick text search and sort for the Developer Action Panel (#2211).
// They work on the rows already loaded in the browser and sit next to the
// Frappe Filter button: the Filter narrows by field, the search box by any text.

// Lower-cased words of the query; every word must appear somewhere in the row.
function words(query) {
	return (query || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
}

function matches(haystackParts, query) {
	const terms = words(query);
	if (!terms.length) return true;
	const haystack = haystackParts
		.filter((v) => v !== null && v !== undefined)
		.map((v) => String(v).toLowerCase())
		.join(" ");
	return terms.every((t) => haystack.includes(t));
}

// Issue rows from get_dev_issues: title, number, project, assignee, labels, parent.
export function issueMatchesSearch(issue, query) {
	return matches(
		[
			issue.title,
			issue.issue_id,
			issue.issue_id != null ? `#${issue.issue_id}` : null,
			issue.project_name,
			issue.project,
			issue.assignee,
			issue.labels,
			issue.parent_issue_id != null ? `#${issue.parent_issue_id}` : null,
		],
		query
	);
}

// Project rows from get_dev_all_projects: name, ID, customer, status.
export function projectMatchesSearch(project, query) {
	return matches(
		[project.project_name, project.name, project.customer_desc, project.customer, project.status],
		query
	);
}

// Same choices as the sort menu before #1895 replaced the filter bar.
export const ISSUE_SORT_OPTIONS = [
	{ value: "due_date:asc", label: "Due date ↑" },
	{ value: "due_date:desc", label: "Due date ↓" },
	{ value: "id:asc", label: "Issue ID ↑" },
	{ value: "id:desc", label: "Issue ID ↓" },
	{ value: "project:asc", label: "Project A–Z" },
	{ value: "title:asc", label: "Title A–Z" },
	{ value: "priority:asc", label: "Priority P1–P3" },
];
export const DEFAULT_ISSUE_SORT = "due_date:asc";

// "P:1" → 1 … "P:3" → 3; no priority label sorts last.
function priority(labels) {
	const found = (labels || "").split(",").map((l) => l.trim()).find((l) => /^P:[1-3]$/.test(l));
	return found ? Number(found.slice(2)) : Infinity;
}

const SORT_KEYS = {
	due_date: (i) => (i.due_date ? new Date(i.due_date).getTime() : null),
	id: (i) => (Number.parseInt(i.issue_id, 10) || 0),
	project: (i) => (i.project_name || i.project || "").toLowerCase(),
	title: (i) => (i.title || "").toLowerCase(),
	priority: (i) => priority(i.labels),
};

// Returns a new sorted list. Issues without a due date stay last in both directions.
export function sortIssues(list, sort = DEFAULT_ISSUE_SORT) {
	const [field, dir] = (sort || DEFAULT_ISSUE_SORT).split(":");
	const key = SORT_KEYS[field] || SORT_KEYS.due_date;
	const sign = dir === "desc" ? -1 : 1;
	return [...list].sort((a, b) => {
		const va = key(a);
		const vb = key(b);
		if (va === vb) return 0;
		if (va === null) return 1;
		if (vb === null) return -1;
		return (va < vb ? -1 : 1) * sign;
	});
}
