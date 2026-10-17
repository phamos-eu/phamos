// Formatting and constants for the Employment Contracts pages of the HR cockpit.

export const CONTRACTS_API = "phamos.api.employment_contracts"

export const CONTRACT_STATUSES = ["Draft", "Upcoming", "Active", "Expired"]

/** Same colours as the Desk list indicator. */
export const CONTRACT_STATUS_THEMES = {
	Draft: "red",
	Upcoming: "blue",
	Active: "green",
	Expired: "gray",
	Cancelled: "red",
}

/** Shared grid for the filter bar and list rows: Employee | Type | Period | FTE | Weekly h | Monthly gross | Status */
export const CONTRACT_GRID =
	"grid grid-cols-[minmax(0,1.6fr)_minmax(0,0.8fr)_minmax(0,1.5fr)_minmax(0,0.6fr)_minmax(0,0.7fr)_minmax(0,1fr)_minmax(0,0.8fr)] gap-x-4"
export const CONTRACT_SUBGRID = "col-span-7 grid grid-cols-subgrid items-center"

const moneyFormatters = new Map()

export function formatMoney(value, currency) {
	if (value == null || Number.isNaN(Number(value))) return "—"
	const key = currency || "EUR"
	if (!moneyFormatters.has(key)) {
		moneyFormatters.set(key, new Intl.NumberFormat(undefined, { style: "currency", currency: key }))
	}
	return moneyFormatters.get(key).format(Number(value))
}

const numberFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 })

export function formatNumber(value) {
	if (value == null || value === "") return "—"
	return numberFormat.format(Number(value))
}

export function formatPercent(value) {
	return value == null ? "—" : `${formatNumber(value)} %`
}

export function formatHours(value) {
	return value == null ? "—" : `${formatNumber(value)} h`
}

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" })

/** "2026-10-20" → localized date, without a timezone shift. */
export function formatDate(value) {
	if (!value) return ""
	const [y, m, d] = String(value).split("-").map(Number)
	return dateFormat.format(new Date(y, m - 1, d))
}

export function formatPeriod(contract) {
	const from = formatDate(contract.effective_from)
	return contract.valid_until ? `${from} – ${formatDate(contract.valid_until)}` : `from ${from}`
}

/** First day of next month, the usual start of a contract change. */
export function firstOfNextMonth() {
	const now = new Date()
	const next = new Date(now.getFullYear(), now.getMonth() + 1, 1)
	const pad = (n) => String(n).padStart(2, "0")
	return `${next.getFullYear()}-${pad(next.getMonth() + 1)}-01`
}

export function errorMessage(error, fallback) {
	const raw = error?.messages?.[0] || error?.message || fallback
	const div = document.createElement("div")
	div.innerHTML = raw
	return div.textContent || fallback
}
