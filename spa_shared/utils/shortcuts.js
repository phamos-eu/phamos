// Keyboard shortcut rules for the cockpits (#1603). Pure helpers, so they can be tested and
// shared; the listeners live in the cockpit that uses them.

// True while the user is typing: shortcuts must not steal letters from fields.
export function isTypingTarget(target) {
	const tag = target?.tagName
	return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || Boolean(target?.isContentEditable)
}

// Dialogs, menus, listboxes and frappe-ui popovers (rendered into #frappeui-popper-root, without
// a role) own their keys.
const OVERLAY = '[role="dialog"], [role="menu"], [role="listbox"], #frappeui-popper-root'

// True when the event comes from inside an overlay.
export function insideOverlay(target) {
	return Boolean(target?.closest?.(OVERLAY))
}

// True while a dialog is open anywhere on the page, wherever focus is (#1608).
export function dialogOpen(root = typeof document !== "undefined" ? document : null) {
	return Boolean(root?.querySelector?.('[role="dialog"]'))
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

// Ctrl/Cmd+S: "save" in Frappe Desk, here the primary action of the open dialog (#2032).
// event.key follows the layout; on a non-Latin one (Cyrillic, Greek) the physical S key counts.
export function isSaveKey(event) {
	if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return false
	const key = String(event.key).toLowerCase()
	return key === "s" || (!/^[a-z]$/.test(key) && event.code === "KeyS")
}

// The frappe-ui dialog on top: Headless UI appends each new one to the body, so the last wins.
// Only frappe-ui (Headless UI) dialogs: full-page surfaces with role="dialog", like the idea
// writing mode, are not confirm dialogs.
const FRAPPE_DIALOG = '[role="dialog"][id^="headlessui-dialog-"]'
export function topDialog(root = typeof document !== "undefined" ? document : null) {
	const dialogs = root?.querySelectorAll?.(FRAPPE_DIALOG)
	return dialogs?.length ? dialogs[dialogs.length - 1] : null
}

// A frappe-ui solid Button, told by the pressed colour only its solid variant has (Button.vue);
// white-text toggles like the appointment weekday chips are not. Red ones are destructive.
// A disabled or loading frappe-ui button loses these classes and looks like any other
// disabled button, so its variant can't be told from the DOM.
// shortcuts.test.js checks these names against the installed frappe-ui Button.vue.
export const SOLID_ACTIVE = ["active:bg-surface-gray-5", "active:bg-blue-700", "active:bg-green-800"]
const isWhite = (button) =>
	button.classList.contains("text-ink-white") &&
	SOLID_ACTIVE.some((name) => button.classList.contains(name)) &&
	!button.hasAttribute?.("aria-pressed")
export const SOLID_RED = "bg-surface-red-5"
const isRed = (button) => button.classList.contains(SOLID_RED)

// What Ctrl/Cmd+S runs in a dialog: a button to click, a form to submit, or null.
// - a button marked data-primary-action wins;
// - otherwise the one enabled solid, non-red button;
// - a dialog without one submits its single form, unless a button is disabled (it may be the
//   greyed-out or loading primary: no double submit) or a red button is the only solid one.
// An ambiguous choice runs nothing: better nothing than the wrong action.
export function dialogPrimaryAction(dialog) {
	if (!dialog) return null
	const marked = dialog.querySelector("[data-primary-action]")
	if (marked) return marked.disabled ? null : marked
	const buttons = [...dialog.querySelectorAll("button")]
	const solid = buttons.filter((b) => isWhite(b) && !isRed(b) && !b.disabled)
	if (solid.length) return solid.length === 1 ? solid[0] : null
	if (buttons.some((b) => b.disabled || isRed(b))) return null
	const forms = dialog.querySelectorAll("form")
	return forms.length === 1 ? forms[0] : null
}

// The Ctrl/Cmd+S handler CockpitShell listens with (capture phase, so a field or editor inside
// the dialog cannot swallow it). While a dialog is open the browser's "Save page" never opens.
export function onDialogSaveKey(event, root = typeof document !== "undefined" ? document : null) {
	if (!isSaveKey(event)) return
	const dialog = topDialog(root)
	if (!dialog) return
	event.preventDefault()
	if (event.repeat || event.isComposing) return
	const action = dialogPrimaryAction(dialog)
	if (action?.tagName === "FORM") action.requestSubmit()
	else action?.click()
}
