/** Desk form URL for a DocType + document name (opens in Desk). */
export function deskRecordUrl(doctype, name) {
	if (!doctype || !name) return "#"
	const slug = String(doctype).trim().toLowerCase().replace(/ /g, "-")
	return `/app/${slug}/${encodeURIComponent(String(name).trim())}`
}
