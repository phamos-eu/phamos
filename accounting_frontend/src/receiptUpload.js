// Upload of receipts (PDFs and e-mails) from the board. Pure helpers + the upload call.

// Cards dragged inside the board carry this type, so the drop zone can ignore them.
export const RECEIPT_CARD_DRAG_TYPE = "application/x-phamos-receipt"

const UPLOAD_METHOD = "phamos.api.accounting_receipts.create_receipts_from_upload"

export function isReceiptFile(file) {
	const name = (file?.name || "").toLowerCase()
	return (
		name.endsWith(".pdf") ||
		name.endsWith(".eml") ||
		file?.type === "application/pdf" ||
		file?.type === "message/rfc822"
	)
}

export function isExternalDrag(event) {
	const types = Array.from(event?.dataTransfer?.types || [])
	return types.length > 0 && !types.includes(RECEIPT_CARD_DRAG_TYPE)
}

// Apple Mail sometimes hands over only a "message:" link instead of the mail itself.
export function droppedMailLink(event) {
	const dt = event?.dataTransfer
	if (!dt) return ""
	const text = dt.getData("text/uri-list") || dt.getData("text/plain") || ""
	return text.trim().startsWith("message:") ? text.trim() : ""
}

function serverMessage(json, fallback) {
	try {
		const messages = JSON.parse(json?._server_messages || "[]")
		const first = messages.length ? JSON.parse(messages[0]) : null
		if (first?.message) return first.message.replace(/<[^>]+>/g, "")
	} catch (e) {
		// fall through
	}
	return json?.exception?.split(":").slice(1).join(":").trim() || fallback
}

export async function uploadReceiptFile(file, { allowDuplicate = false } = {}) {
	const body = new FormData()
	body.append("file", file, file.name)
	body.append("is_private", "1")
	body.append("method", UPLOAD_METHOD)
	if (allowDuplicate) body.append("allow_duplicate", "1")
	const response = await fetch("/api/method/upload_file", {
		method: "POST",
		body,
		headers: { Accept: "application/json", "X-Frappe-CSRF-Token": window.csrf_token || "" },
	})
	const json = await response.json().catch(() => ({}))
	if (!response.ok) throw new Error(serverMessage(json, `Upload failed (${response.status})`))
	return json.message?.results || []
}
