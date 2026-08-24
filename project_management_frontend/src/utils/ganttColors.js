export function parseDependsOn(dependsOnTasks) {
	if (!dependsOnTasks) return []
	return String(dependsOnTasks)
		.split(",")
		.map((s) => s.trim())
		.filter(Boolean)
}

export function isValidHexColor(color) {
	return /^#[0-9A-Fa-f]{6}$/.test(color || "")
}

export function taskColorClass(color) {
	if (!isValidHexColor(color)) return ""
	return `color-${color.slice(1).toUpperCase()}`
}

function hexToRgb(hex) {
	return {
		r: parseInt(hex.slice(1, 3), 16),
		g: parseInt(hex.slice(3, 5), 16),
		b: parseInt(hex.slice(5, 7), 16),
	}
}

function rgbToHex(r, g, b) {
	const clamp = (n) => Math.max(0, Math.min(255, Math.round(n)))
	return `#${[clamp(r), clamp(g), clamp(b)]
		.map((n) => n.toString(16).padStart(2, "0"))
		.join("")}`
}

function luminance(hex) {
	const { r, g, b } = hexToRgb(hex)
	return (0.299 * r + 0.587 * g + 0.114 * b) / 255
}

/** Tonal variant for progress fill — same hue, darker or lighter depending on base. */
export function progressTone(hex) {
	const { r, g, b } = hexToRgb(hex)
	const factor = luminance(hex) > 0.55 ? 0.72 : 1.28
	return rgbToHex(r * factor, g * factor, b * factor)
}

export function contrastColor(hex) {
	const lum = luminance(hex)
	return lum > 0.6 ? "#333333" : "#ffffff"
}

export function buildBarColorCss(tasks) {
	const classes = new Set()
	for (const task of tasks) {
		const cls = task.custom_class || ""
		for (const part of cls.split(/\s+/)) {
			if (part.startsWith("color-")) classes.add(part)
		}
	}

	return [...classes]
		.map((className) => {
			const hex = `#${className.slice(6)}`
			const progress = progressTone(hex)
			return `
.gantt .bar-wrapper.${className} .bar { fill: ${hex}; }
.gantt .bar-wrapper.${className} .bar-progress { fill: ${progress}; }
`
		})
		.join("")
}
