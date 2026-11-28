// Formatting and constants for Employment Contracts, shared by the HR and Personal cockpits.

import { formatDate as formatSystemDate } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"

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

const rateFormat = new Intl.NumberFormat(undefined, { maximumSignificantDigits: 6 })

/** Exchange rates need significant digits, not two decimals (1 KES = 0.00702 EUR). */
export function formatRate(value) {
	if (value == null || value === "") return "—"
	return rateFormat.format(Number(value))
}

export function formatPercent(value) {
	return value == null ? "—" : `${formatNumber(value)} %`
}

export function formatHours(value) {
	return value == null ? "—" : `${formatNumber(value)} h`
}

export function formatDays(value) {
	return value == null ? "—" : __("{0} days", [formatNumber(value)])
}

/** A fraction of at least half a day rounds up to a whole day (BUrlG § 5 (2)); a smaller one stays. */
function roundLeaveDays(days) {
	const whole = Math.floor(days + 1e-9)
	return days - whole >= 0.5 - 1e-9 ? whole + 1 : Math.round(days * 100) / 100
}

/** Full-time leave days (five-day week) converted to the contract's working days. */
export function leaveDaysPerYear(fullTimeLeaveDays, workingDaysPerWeek) {
	return roundLeaveDays((Number(fullTimeLeaveDays || 0) * Number(workingDaysPerWeek || 0)) / 5)
}

/** Pro rata for a contract shorter than a year: 1/12 per full month. Mirrors employment_contract.py. */
export function prorateLeaveDays(yearly, effectiveFrom, validUntil) {
	if (!effectiveFrom || !validUntil) return yearly
	const toUtc = (value) => {
		const [y, m, d] = value.split("-").map(Number)
		return new Date(Date.UTC(y, m - 1, d))
	}
	const start = toUtc(effectiveFrom)
	// Valid Until is the last day of the contract, so full months run up to the day after.
	const end = toUtc(validUntil)
	end.setUTCDate(end.getUTCDate() + 1)
	let months = (end.getUTCFullYear() - start.getUTCFullYear()) * 12 + (end.getUTCMonth() - start.getUTCMonth())
	if (end.getUTCDate() < start.getUTCDate()) months -= 1
	if (months >= 12) return yearly
	return roundLeaveDays((yearly * Math.max(months, 0)) / 12)
}

/** "2026-10-20" → the site's date format, without a timezone shift. */
export function formatDate(value) {
	return value ? formatSystemDate(value) : ""
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

/**
 * Plain text of a server error. Frappe messages contain HTML (links, bold); DOMParser
 * builds an inert document, so markup in the message can't run scripts or load images
 * the way innerHTML on a detached element can.
 */
export function errorMessage(error, fallback) {
	const raw = String(error?.messages?.[0] || error?.message || fallback)
	const text = new DOMParser().parseFromString(raw, "text/html").body.textContent
	return text?.trim() || fallback
}
