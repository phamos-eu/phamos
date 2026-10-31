/**
 * The excerpt on an idea card without the title in front (#1773). A side idea's text starts with
 * its title line, so the card would show it twice. DOM-free for Vitest.
 */
export function summaryWithoutTitle(summary, title) {
	const text = String(summary || "").trim()
	const head = String(title || "").trim()
	if (!head || !text.toLowerCase().startsWith(head.toLowerCase())) return text
	return text.slice(head.length).replace(/^[\s.,:;…—-]+/, "")
}
