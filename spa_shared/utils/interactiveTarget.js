// Whether a click landed on something that takes its own clicks (a field, an editor, a button,
// a link, a menu), looking only up to `boundary`. Used where a click on a card's free area does
// something itself, e.g. closing an open checklist item (#1921).

export const INTERACTIVE_SELECTOR =
	'input, textarea, select, button, a, label, [contenteditable], .ProseMirror, [role="combobox"], [role="listbox"], [role="option"], [role="menu"], [role="menuitem"], [role="dialog"]'

/**
 * @param {Element} target the clicked element
 * @param {Element} boundary the card; it and its ancestors are not looked at (a card may itself be
 *   role="button")
 */
export function isInteractiveTarget(target, boundary, selector = INTERACTIVE_SELECTOR) {
	for (let el = target; el && el !== boundary; el = el.parentElement) {
		if (el.matches?.(selector)) return true
	}
	return false
}
