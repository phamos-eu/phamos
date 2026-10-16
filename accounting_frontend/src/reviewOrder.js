// The list a receipt was opened from (queue or all receipts), so review mode can step
// to the previous / next receipt in the same order. Kept per browser tab.
const KEY = "accounting-receipt-review-order"

export function setReviewOrder(names, origin) {
	try {
		sessionStorage.setItem(KEY, JSON.stringify({ names, origin }))
	} catch (e) {
		// private mode: review mode falls back to the queue order
	}
}

export function getReviewOrder() {
	try {
		return JSON.parse(sessionStorage.getItem(KEY) || "null")
	} catch (e) {
		return null
	}
}

export function neighbours(names, current) {
	const index = names.indexOf(current)
	if (index === -1) return { index: -1, previous: null, next: names[0] || null }
	return { index, previous: names[index - 1] || null, next: names[index + 1] || null }
}
