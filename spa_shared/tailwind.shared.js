/** Shared Tailwind content/theme; SPAs pass frappe-ui preset (resolved from their node_modules). */
export function makeConfig(frappeUIPreset) {
	return {
		// Match frappe-ui: CSS vars and `dark:` variants follow data-theme
		// (set by spa_shared/theme.js from prefers-color-scheme).
		darkMode: ["selector", '[data-theme="dark"]'],
		presets: [frappeUIPreset],
		content: [
			"./index.html",
			"./src/**/*.{vue,js,ts,jsx,tsx}",
			"../spa_shared/**/*.{vue,js,ts,jsx,tsx}",
			"../frontend/src/**/*.{vue,js,ts,jsx,tsx}",
			"./node_modules/frappe-ui/src/components/**/*.{vue,js,ts,jsx,tsx}",
		],
		theme: {
			extend: {},
		},
		plugins: [],
	}
}
