/**
 * Keep frappe-ui CSS tokens in sync with OS prefers-color-scheme.
 * Tokens and `dark:` variants follow `[data-theme="dark"]` (see spa_shared/tailwind.shared.js).
 */
export function syncThemeFromMediaPreference() {
	const mq = window.matchMedia("(prefers-color-scheme: dark)")

	const apply = () => {
		const dark = mq.matches
		document.documentElement.dataset.theme = dark ? "dark" : "light"
		const meta = document.querySelector('meta[name="theme-color"]')
		if (meta) {
			meta.setAttribute(
				"content",
				dark
					? getComputedStyle(document.documentElement).getPropertyValue("--surface-gray-1").trim() ||
							"#232323"
					: getComputedStyle(document.documentElement).getPropertyValue("--surface-gray-1").trim() ||
							"#F8F8F8"
			)
		}
	}

	apply()
	if (typeof mq.addEventListener === "function") {
		mq.addEventListener("change", apply)
	} else if (typeof mq.addListener === "function") {
		mq.addListener(apply)
	}
}
