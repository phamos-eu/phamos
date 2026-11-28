// Find-in-page for the cockpits (#1592): case- and accent-insensitive matching on plain text.

const fold = (text) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()

// Start offsets of every match of `query` in `text` (no overlaps). Folding keeps lengths equal
// for the characters that occur in cockpit text, so offsets map back onto the original.
export function findMatches(text, query) {
	const needle = fold(String(query || "").trim())
	if (!needle || !text) return []
	const haystack = fold(String(text))
	if (haystack.length !== String(text).length) {
		// Folding changed the length (rare combined characters): fall back to a lower-case search.
		return scan(String(text).toLowerCase(), needle.toLowerCase())
	}
	return scan(haystack, needle)
}

function scan(haystack, needle) {
	const result = []
	let index = haystack.indexOf(needle)
	while (index !== -1) {
		result.push(index)
		index = haystack.indexOf(needle, index + needle.length)
	}
	return result
}

// Next index when stepping through `count` matches (wraps around).
export function stepIndex(current, count, direction) {
	if (!count) return -1
	if (current < 0) return direction < 0 ? count - 1 : 0
	return (current + direction + count) % count
}
