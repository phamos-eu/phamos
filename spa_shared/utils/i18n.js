/** Client-side gettext using messages from SPA boot (`frappe.boot.__messages`). */
export function __(text, replace) {
	if (!text) return text
	const messages = (typeof window !== "undefined" && window.frappe?.boot?.__messages) || {}
	let translated = messages[text] || text
	if (replace && typeof replace === "object") {
		for (const [key, value] of Object.entries(replace)) {
			translated = translated.replace(`{${key}}`, value)
		}
	} else if (Array.isArray(replace)) {
		replace.forEach((value, idx) => {
			translated = translated.replace(`{${idx}}`, value)
		})
	}
	return translated
}
