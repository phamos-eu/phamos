/**
 * Receivables view (#1777): grid tracks shared by header and rows, bucket colours, and the
 * client-side search, filter and sort over the payload of `get_receivables`.
 */

/** Customer | Contact | Outstanding | Overdue | Not yet due | Oldest | Aging | Last contact | Desk */
export const CUSTOMER_GRID =
	"grid grid-cols-[1.5rem_minmax(0,2fr)_minmax(0,1.6fr)_7rem_7rem_7rem_5rem_minmax(6rem,1fr)_7.5rem_2rem] gap-x-4"
export const CUSTOMER_COLS = "col-span-10 grid grid-cols-subgrid items-center"

/** Invoice | Customer | Contact | Due | Outstanding | Age | Last contact | Desk */
export const INVOICE_GRID =
	"grid grid-cols-[minmax(0,1.5fr)_minmax(0,1.6fr)_minmax(0,1.5fr)_8.5rem_7.5rem_7.5rem_7.5rem_2rem] gap-x-4"
export const INVOICE_COLS = "col-span-8 grid grid-cols-subgrid items-center"

/** Nested under a customer: the same columns without Customer. */
export const NESTED_INVOICE_GRID =
	"grid grid-cols-[minmax(0,1.5fr)_minmax(0,1.5fr)_8.5rem_7.5rem_7.5rem_7.5rem_2rem] gap-x-4"
export const NESTED_INVOICE_COLS = "col-span-7 grid grid-cols-subgrid items-center"

/** Short labels for the age bucket badge and the expanded customer strip. */
export const BUCKET_SHORT = {
	not_due: "Not due",
	d1_30: "1–30 d",
	d31_60: "31–60 d",
	d61_90: "61–90 d",
	d91_120: "91–120 d",
	d120_plus: "> 120 d",
}
export const BUCKET_ORDER = Object.keys(BUCKET_SHORT)

/** frappe-ui Badge themes per bucket. */
export const BUCKET_BADGE = {
	not_due: "green",
	d1_30: "orange",
	d31_60: "red",
	d61_90: "red",
	d91_120: "red",
	d120_plus: "red",
}

/** Bar colours for the stacked aging bar (frappe-ui theme variables, light and dark). */
export const BUCKET_COLORS = {
	not_due: "var(--ink-green-3)",
	d1_30: "var(--ink-amber-3)",
	d31_60: "var(--ink-red-2)",
	d61_90: "var(--ink-red-3)",
	d91_120: "var(--ink-red-4)",
	d120_plus: "var(--ink-red-5, var(--ink-red-4))",
}

export const SORT_OPTIONS = [
	{ value: "overdue", label: "Most overdue" },
	{ value: "outstanding", label: "Largest outstanding" },
	{ value: "oldest", label: "Oldest overdue" },
	{ value: "name", label: "Customer A–Z" },
]

export const DEFAULT_FILTERS = { view: "customers", q: "", overdue: "", bucket: "", sort: "overdue", company: "" }

function text(value) {
	return String(value ?? "").toLowerCase()
}

/** True when the search text appears in the invoice's number, PO, customer or contact. */
export function invoiceMatches(item, query) {
	const q = text(query).trim()
	if (!q) return true
	return [item.voucher_no, item.po_no, item.customer, item.customer_name, item.contact?.name, item.contact?.email]
		.some((value) => text(value).includes(q))
}

/** True when the search text appears in the customer's name, ID or contact. */
export function customerMatches(customer, query) {
	const q = text(query).trim()
	if (!q) return true
	return [customer.customer, customer.customer_name, customer.contact?.name, customer.contact?.email]
		.some((value) => text(value).includes(q))
}

/** Invoice filter for the toggles: overdue only, one age bucket. Credits pass only when neither is set. */
export function invoicePasses(item, { overdue, bucket }) {
	if (bucket) return item.bucket === bucket
	if (overdue) return item.kind === "invoice" && item.days_overdue > 0
	return true
}

const INVOICE_SORTS = {
	overdue: (a, b) => b.days_overdue - a.days_overdue || b.outstanding - a.outstanding,
	outstanding: (a, b) => b.outstanding - a.outstanding,
	oldest: (a, b) => b.days_overdue - a.days_overdue || b.outstanding - a.outstanding,
	name: (a, b) => text(a.customer_name).localeCompare(text(b.customer_name)) || b.days_overdue - a.days_overdue,
}

/** Sorted copy; credits always last. */
export function sortInvoices(items, sort) {
	const compare = INVOICE_SORTS[sort] || INVOICE_SORTS.overdue
	return [...items].sort((a, b) => (a.kind === b.kind ? compare(a, b) : a.kind === "credit" ? 1 : -1))
}

const CUSTOMER_SORTS = {
	overdue: (a, b) => b.overdue - a.overdue || b.outstanding - a.outstanding,
	outstanding: (a, b) => b.outstanding - a.outstanding,
	oldest: (a, b) => b.oldest_days_overdue - a.oldest_days_overdue || b.overdue - a.overdue,
	name: (a, b) => text(a.customer_name).localeCompare(text(b.customer_name)),
}

export function sortCustomers(customers, sort) {
	return [...customers].sort(CUSTOMER_SORTS[sort] || CUSTOMER_SORTS.overdue)
}

/** customer → its items, in the order given. */
export function groupInvoices(items) {
	const groups = {}
	for (const item of items) (groups[item.customer] ||= []).push(item)
	return groups
}

/** "40 d overdue", "due in 5 d", "due today", "no due date". */
export function dueText(item) {
	if (item.kind === "credit") return ""
	if (item.days_overdue > 0) return `${item.days_overdue} d overdue`
	if (!item.due_date) return "no due date"
	const due = new Date(`${item.due_date}T00:00:00`)
	const today = new Date()
	today.setHours(0, 0, 0, 0)
	const days = Math.round((due - today) / 86400000)
	return days <= 0 ? "due today" : `due in ${days} d`
}

/** "Email" or "Dunning L2". */
export function lastContactKind(last) {
	if (!last) return ""
	if (last.kind === "dunning") return last.level ? `Dunning L${last.level}` : "Dunning"
	return "Email"
}
