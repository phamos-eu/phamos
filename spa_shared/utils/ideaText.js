/**
 * Plain text for the writing mode of an idea (#1774). The Idea page edits rich text; the writing
 * mode edits a plain textarea, so the content is flattened on the way in and written back as
 * paragraphs. Lossy by design (headings and lists become lines). DOM-free for Vitest.
 */

const ENTITIES = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&nbsp;": " " }

export function htmlToPlainText(html) {
	return String(html || "")
		.replace(/<br\s*\/?>/gi, "\n")
		.replace(/<\/(p|div|li|h[1-6]|blockquote|pre)>/gi, "\n\n")
		.replace(/<[^>]+>/g, "")
		.replace(/&(amp|lt|gt|quot|#39|nbsp);/g, (m) => ENTITIES[m])
		.replace(/[ \t]+\n/g, "\n")
		.replace(/\n{3,}/g, "\n\n")
		.trim()
}

function escape(text) {
	return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

/** Blank line = new paragraph, single newline = line break. */
export function plainTextToHtml(text) {
	const paragraphs = String(text || "")
		.replace(/\r\n/g, "\n")
		.split(/\n\s*\n/)
		.map((p) => p.trim())
		.filter(Boolean)
	return paragraphs.map((p) => `<p>${escape(p).replace(/\n/g, "<br>")}</p>`).join("")
}

export function countWords(text) {
	const t = String(text || "").trim()
	return t ? t.split(/\s+/).length : 0
}

/** Same factors as phamos.cockpits.defaults.IDEA_AIM_FACTORS. */
export const AIM_FACTORS = { more: 1.15, similar: 1, less: 0.85 }

export function wordGoal(lastWords, aim, base = 300) {
	return Math.round((Number(lastWords) || base) * (AIM_FACTORS[aim] ?? 1))
}
