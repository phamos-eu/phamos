// Links in Ophice chat messages (#2169). A message is split into text and link parts, so the chat
// can show links as <a> without v-html: whatever someone types stays text, never markup.

// http(s):// or www., not inside a word, an e-mail address or a longer path.
const URL_RE = /(?<![\w.@/:-])(?:https?:\/\/|www\.)[^\s<>"]+/gi

// Characters that usually end a sentence, not the address.
const TRAILING = ".,;:!?'\""

/** Cuts sentence punctuation and an unpaired closing bracket off the end of a found address. */
function trimEnd(url) {
	let end = url.length
	for (;;) {
		const last = url[end - 1]
		if (TRAILING.includes(last)) {
			end--
			continue
		}
		const pair = { ")": "(", "]": "[", "}": "{" }[last]
		if (pair) {
			const part = url.slice(0, end)
			if (part.split(last).length > part.split(pair).length) {
				end--
				continue
			}
		}
		return url.slice(0, end)
	}
}

/**
 * Splits a chat message into parts: `{ text }` for plain text, `{ text, href }` for a link.
 * `www.` addresses get `https://`. Only http(s) links come out, never `javascript:` or the like.
 */
export function chatParts(message) {
	const text = message == null ? "" : String(message)
	const parts = []
	let at = 0
	for (const match of text.matchAll(URL_RE)) {
		const url = trimEnd(match[0])
		// "www." alone, or "https://" with nothing after it, is no address.
		if (/^(?:https?:\/\/|www\.)$/i.test(url)) continue
		if (match.index > at) parts.push({ text: text.slice(at, match.index) })
		const href = /^www\./i.test(url) ? `https://${url}` : url
		parts.push({ text: url, href })
		at = match.index + url.length
	}
	if (at < text.length) parts.push({ text: text.slice(at) })
	return parts
}
