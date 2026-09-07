/**
 * Keep frappe-ui CSS tokens in sync with OS prefers-color-scheme.
 * Tailwind dark: already uses darkMode: "media"; frappe-ui needs data-theme.
 */
export function syncThemeFromMediaPreference() {
	const mq = window.matchMedia("(prefers-color-scheme: dark)")

	const apply = () => {
		const dark = mq.matches
		document.documentElement.dataset.theme = dark ? "dark" : "light"
		const meta = document.querySelector('meta[name="theme-color"]')
		if (meta) meta.setAttribute("content", dark ? "#111827" : "#ffffff")
	}

	apply()
	if (typeof mq.addEventListener === "function") {
		mq.addEventListener("change", apply)
	} else if (typeof mq.addListener === "function") {
		mq.addListener(apply)
	}
}
