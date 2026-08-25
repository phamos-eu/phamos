/** Shared Tailwind content/theme; SPAs pass frappe-ui preset (resolved from their node_modules). */
export function makeConfig(frappeUIPreset) {
	return {
		darkMode: "media",
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
