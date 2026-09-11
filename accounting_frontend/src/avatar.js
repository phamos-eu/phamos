/**
 * Desk-style avatar helpers matching Frappe Framework avatar_group / get_palette.
 * @see frappe/public/js/frappe/utils/common.js
 * @see frappe/public/scss/desk/avatar.scss
 */

const PALETTE = [
	{ key: "orange" },
	{ key: "pink" },
	{ key: "blue" },
	{ key: "green" },
	{ key: "dark-green" },
	{ key: "red" },
	{ key: "yellow" },
	{ key: "purple" },
]

/** Lightweight hash approximating Frappe's md5-based palette index. */
function paletteIndex(txt) {
	const s = String(txt || "")
	let hash = 0
	for (let i = 0; i < s.length; i++) {
		hash = (hash * 31 + s.charCodeAt(i)) >>> 0
	}
	return hash % 8
}

/**
 * Palette key for initials. Seed with the same display label everywhere (list + detail)
 * so the same assignee always gets the same color.
 */
export function getAvatarPalette(label) {
	return PALETTE[paletteIndex(label || "?")]
}

/** Frappe get_abbr — up to maxLength initials from words. */
export function getAvatarAbbr(txt, maxLength = 2) {
	if (!txt) return "?"
	let abbr = ""
	for (const word of String(txt).split(/\s+/)) {
		const w = word.trim()
		if (!w) continue
		abbr += w[0]
		if (abbr.length >= maxLength) break
	}
	return (abbr || "?").toUpperCase()
}

export function assigneeUsersFromRow(row) {
	const ids = row?.assignees || []
	const names = row?.assignee_names || []
	const images = row?.assignee_images || []
	return ids.map((id, i) => ({
		name: id,
		full_name: names[i] || id,
		user_image: images[i] || "",
	}))
}
