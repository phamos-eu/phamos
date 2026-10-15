// Eisenhower matrix rules for the Personal Cockpit (#1555). The server decides the quadrant
// (phamos.api.personal_todo_matrix); these helpers mirror it for drag & drop feedback.

export const QUADRANTS = [
	{
		key: "do",
		label: "Do now",
		hint: "Important and urgent",
		important: true,
		urgent: true,
		shortcut: "1",
		theme: "red",
	},
	{
		key: "schedule",
		label: "Schedule",
		hint: "Important, not urgent: give it a day",
		important: true,
		urgent: false,
		shortcut: "2",
		theme: "blue",
	},
	{
		key: "delegate",
		label: "Hand off or batch",
		hint: "Urgent, not important",
		important: false,
		urgent: true,
		shortcut: "3",
		theme: "orange",
	},
	{
		key: "eliminate",
		label: "Drop or let go",
		hint: "Neither important nor urgent",
		important: false,
		urgent: false,
		shortcut: "4",
		theme: "gray",
	},
]

const BY_KEY = Object.fromEntries(QUADRANTS.map((q) => [q.key, q]))
const BY_SHORTCUT = Object.fromEntries(QUADRANTS.map((q) => [q.shortcut, q.key]))

export function quadrant(key) {
	return BY_KEY[key] || null
}

export function quadrantForShortcut(key) {
	return BY_SHORTCUT[key] || null
}

function isoDate(value) {
	return value ? String(value).slice(0, 10) : ""
}

export function isUrgent(todo, urgentUntil) {
	const date = isoDate(todo?.date)
	return Boolean(date) && date <= isoDate(urgentUntil)
}

export function quadrantOf(todo, urgentUntil) {
	const important = Boolean(todo?.important)
	const urgent = isUrgent(todo, urgentUntil)
	return QUADRANTS.find((q) => q.important === important && q.urgent === urgent).key
}

// What a move from the ToDo's current quadrant to `targetKey` needs from the user:
// a new later date when it leaves "urgent", and the payoff question when it becomes important.
export function moveNeeds(todo, targetKey, urgentUntil) {
	const target = quadrant(targetKey)
	if (!target) return null
	const urgentNow = isUrgent(todo, urgentUntil)
	return {
		same: quadrantOf(todo, urgentUntil) === targetKey,
		laterDate: !target.urgent && urgentNow,
		dueSoon: target.urgent && !urgentNow,
		payoff: target.important && !todo?.important,
	}
}
