// Keyboard shortcut rules for the cockpits (#1603). Pure helpers, so they can be tested and
// shared; the listeners live in the cockpit that uses them.

// True while the user is typing: shortcuts must not steal letters from fields.
export function isTypingTarget(target) {
	const tag = target?.tagName
	return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || Boolean(target?.isContentEditable)
}

// True when the event comes from inside an open dialog or menu, which own their keys.
export function insideOverlay(target) {
	return Boolean(target?.closest?.('[role="dialog"], [role="menu"], [role="listbox"]'))
}

// Plain key without Ctrl, Cmd or Alt (Shift is allowed: "?" needs it).
export function isPlainKey(event) {
	return !event.ctrlKey && !event.metaKey && !event.altKey
}

// Ctrl/Cmd+B: "new" in Frappe Desk, here the Create menu.
export function isCreateKey(event) {
	return Boolean(event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && String(event.key).toLowerCase() === "b"
}

// Direction for list navigation: +1 / -1, or 0 when the key does not move.
// j/k always work; the arrow keys only once focus is on a list row, so they still scroll pages.
export function listDirection(event, onListItem) {
	if (!isPlainKey(event) || event.shiftKey) return 0
	if (event.key === "j") return 1
	if (event.key === "k") return -1
	if (!onListItem) return 0
	if (event.key === "ArrowDown") return 1
	if (event.key === "ArrowUp") return -1
	return 0
}

// Next row index; stays at the ends instead of wrapping (a list is not a carousel).
// From no focus (-1), down starts at the top and up at the bottom.
export function nextListIndex(current, count, direction) {
	if (!count || !direction) return -1
	if (current < 0) return direction > 0 ? 0 : count - 1
	return Math.min(count - 1, Math.max(0, current + direction))
}
