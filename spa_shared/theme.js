/**
 * Keep frappe-ui CSS tokens in sync with OS prefers-color-scheme.
 * Tokens and `dark:` variants follow `[data-theme="dark"]` (see spa_shared/tailwind.shared.js).
 *
 * The page's theme-color (an installed cockpit's window title bar) is the cockpit colour from
 * Cockpit Settings in light and dark mode (#1933); without one it follows the page background.
 */
export function syncThemeFromMediaPreference() {
	const mq = window.matchMedia("(prefers-color-scheme: dark)")
	const cockpitColor = window.frappe?.boot?.cockpit_window?.color

	const apply = () => {
		const dark = mq.matches
		document.documentElement.dataset.theme = dark ? "dark" : "light"
		const meta = document.querySelector('meta[name="theme-color"]')
		if (meta) {
			const background =
				getComputedStyle(document.documentElement).getPropertyValue("--surface-gray-1").trim() ||
				(dark ? "#232323" : "#F8F8F8")
			meta.setAttribute("content", cockpitColor || background)
		}
	}

	apply()
	if (typeof mq.addEventListener === "function") {
		mq.addEventListener("change", apply)
	} else if (typeof mq.addListener === "function") {
		mq.addListener(apply)
	}
}
