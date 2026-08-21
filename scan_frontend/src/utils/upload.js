/** Read a File as base64 (without data: prefix).
 * Prefer arrayBuffer — more reliable than readAsDataURL on iOS Safari
 * after the file picker closes.
 */
export async function fileToBase64(file) {
	if (!file) {
		throw new Error("No file selected")
	}

	// Prefer ArrayBuffer path (avoids Safari FileReader permission quirks)
	if (typeof file.arrayBuffer === "function") {
		const buffer = await file.arrayBuffer()
		const bytes = new Uint8Array(buffer)
		return uint8ToBase64(bytes)
	}

	return new Promise((resolve, reject) => {
		const reader = new FileReader()
		reader.onload = () => {
			const result = String(reader.result || "")
			const base64 = result.includes(",") ? result.split(",", 1)[1] : result
			resolve(base64)
		}
		reader.onerror = () =>
			reject(
				reader.error ||
					new Error(
						"The selected file could not be read. Please try again or pick another file."
					)
			)
		reader.readAsDataURL(file)
	})
}

function uint8ToBase64(bytes) {
	const chunkSize = 0x8000
	let binary = ""
	for (let i = 0; i < bytes.length; i += chunkSize) {
		const chunk = bytes.subarray(i, i + chunkSize)
		binary += String.fromCharCode.apply(null, chunk)
	}
	return btoa(binary)
}

export function formatRelativeTime(value) {
	if (!value) return ""
	const date = new Date(value)
	if (Number.isNaN(date.getTime())) return String(value)
	const diffMs = Date.now() - date.getTime()
	const mins = Math.floor(diffMs / 60000)
	if (mins < 1) return "Just now"
	if (mins < 60) return `${mins}m ago`
	const hours = Math.floor(mins / 60)
	if (hours < 24) return `${hours}h ago`
	const days = Math.floor(hours / 24)
	if (days < 7) return `${days}d ago`
	return date.toLocaleDateString()
}

export function statusClass(status) {
	const key = String(status || "Draft").toLowerCase()
	if (key === "processing") return "scan-status-chip--processing"
	if (key === "ready" || key === "done") return "scan-status-chip--ready"
	return "scan-status-chip--draft"
}
