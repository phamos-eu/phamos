/**
 * Desk-style avatar helpers matching Frappe Framework avatar_group / get_palette.
 * @see frappe/public/js/frappe/utils/common.js
 * @see frappe/public/scss/desk/avatar.scss
 */

/** Light / dark hex values matching Frappe espresso avatar tokens. */
const PALETTE = [
	{ key: "orange", bg: "#fff1e7", color: "#d45a08", darkBg: "#d45a08", darkColor: "#fff1e7" },
	{ key: "pink", bg: "#fff7fc", color: "#e34aa6", darkBg: "#e34aa6", darkColor: "#fff7fc" },
	{ key: "blue", bg: "#f7fbfd", color: "#0289f7", darkBg: "#0289f7", darkColor: "#f7fbfd" },
	{ key: "green", bg: "#daf0e1", color: "#16794c", darkBg: "#16794c", darkColor: "#daf0e1" },
	{ key: "dark-green", bg: "#daf0e1", color: "#16794c", darkBg: "#16794c", darkColor: "#daf0e1" },
	{ key: "red", bg: "#fff7f7", color: "#e03636", darkBg: "#e03636", darkColor: "#fff7f7" },
	{ key: "yellow", bg: "#fffcef", color: "#edba13", darkBg: "#edba13", darkColor: "#fffcef" },
	{ key: "purple", bg: "#fdfaff", color: "#9c45e3", darkBg: "#9c45e3", darkColor: "#fdfaff" },
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
 * Palette for initials. Seed with the same display label everywhere (list + detail)
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
