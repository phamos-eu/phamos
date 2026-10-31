<template>
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-7xl flex-col gap-4">
			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ error }}
			</div>
			<div v-if="loading && !data" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
				Loading receivables…
			</div>

			<template v-if="data">
				<div class="flex flex-wrap items-center justify-between gap-2 text-sm text-ink-gray-6">
					<span>{{ data.company }} · {{ data.currency }} · as of {{ asOf }}</span>
					<div class="flex items-center gap-2">
						<select
							v-if="data.companies.length > 1"
							:value="data.company"
							class="input"
							aria-label="Company"
							@change="selectCompany($event.target.value)"
						>
							<option v-for="name in data.companies" :key="name" :value="name">{{ name }}</option>
						</select>
						<Button icon-left="refresh-cw" label="Refresh" :loading="loading" @click="load" />
					</div>
				</div>

				<section class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
					<StatCard
						label="Outstanding"
						:value="money(totals.outstanding)"
						:hint="`${pluralize(totals.invoice_count, 'invoice', 'invoices')} · ${pluralize(totals.customer_count, 'customer', 'customers')}`"
						:lines="totals.credits_count ? [`incl. ${money(totals.credits_amount)} unallocated credit`] : []"
					/>
					<StatCard label="Overdue" :value="money(totals.overdue_amount)">
						<button
							v-if="totals.overdue_count"
							type="button"
							class="mt-1 text-left text-xs font-medium text-ink-red-4 hover:underline"
							@click="showOverdue"
						>
							{{ pluralize(totals.overdue_count, "invoice", "invoices") }} · {{ pluralize(totals.customers_overdue, "customer", "customers") }}
						</button>
						<div v-else class="mt-1 text-xs text-ink-gray-6">Nothing overdue</div>
					</StatCard>
					<StatCard
						label="Not yet due"
						:value="money(totals.not_due_amount)"
						:hint="pluralize(totals.not_due_count, 'invoice', 'invoices')"
					/>
					<StatCard
						label="Oldest overdue"
						:value="totals.oldest_days_overdue ? `${totals.oldest_days_overdue} days` : '—'"
						:hint="totals.oldest_customer_name || 'Nothing overdue'"
					/>
				</section>

				<HorizontalBars
					title="Outstanding by age"
					:rows="data.buckets"
					:format="(value, row) => `${value} · ${money(row.amount)}`"
					selectable
					empty-text="Nothing outstanding."
					@select="selectBucket"
				/>

				<section class="rounded-lg border border-outline-gray-2 bg-surface-white">
					<div class="flex flex-wrap items-center gap-3 border-b border-outline-gray-2 px-4 py-3 text-sm">
						<div class="inline-flex rounded-md bg-surface-gray-2 p-0.5" role="tablist" aria-label="Layout">
							<button
								v-for="option in VIEWS"
								:key="option.value"
								type="button"
								role="tab"
								:aria-selected="filters.view === option.value"
								class="rounded px-3 py-1"
								:class="filters.view === option.value ? 'bg-surface-white font-medium text-ink-gray-9 shadow-sm' : 'text-ink-gray-6'"
								@click="filters.view = option.value"
							>
								{{ option.label }}
							</button>
						</div>
						<input
							ref="search"
							v-model="filters.q"
							type="search"
							class="input w-64"
							placeholder="Customer, invoice, PO, contact…"
							aria-label="Search"
							@keydown.esc="filters.q = ''"
						/>
						<label class="flex items-center gap-1.5 text-ink-gray-7">
							<input v-model="overdueOnly" type="checkbox" />
							Overdue only
						</label>
						<span
							v-if="filters.bucket"
							class="inline-flex items-center gap-1 rounded-full bg-surface-gray-2 py-0.5 pl-2.5 pr-1 text-xs text-ink-gray-8"
						>
							{{ bucketLabel }}
							<button type="button" class="rounded-full px-1 hover:bg-surface-gray-3" title="Show all ages" @click="filters.bucket = ''">×</button>
						</span>
						<label class="ml-auto flex items-center gap-1.5 text-ink-gray-6">
							Sort
							<select v-model="filters.sort" class="input">
								<option v-for="option in SORT_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
							</select>
						</label>
					</div>

					<div class="overflow-x-auto">
						<div v-if="filters.view === 'customers'" :class="[CUSTOMER_GRID, 'min-w-[68rem]']">
							<div :class="[CUSTOMER_COLS, HEADER_CLASS]">
								<span />
								<span>Customer</span>
								<span>Contact</span>
								<span class="text-right">Outstanding</span>
								<span class="text-right">Overdue</span>
								<span class="text-right">Not yet due</span>
								<span class="text-right">Oldest</span>
								<span>Aging</span>
								<span>Last contact</span>
								<span />
							</div>
							<ReceivableCustomerRow
								v-for="customer in visibleCustomers"
								:key="customer.customer"
								:customer="customer"
								:invoices="itemsByCustomer[customer.customer] || []"
								:currency="data.currency"
								:expanded="expanded.has(customer.customer) || autoExpanded.has(customer.customer)"
								@toggle="toggle(customer.customer)"
							/>
							<p v-if="!visibleCustomers.length" class="col-span-10 px-4 py-10 text-center text-sm text-ink-gray-5">
								{{ emptyText }}
							</p>
						</div>

						<div v-else :class="[INVOICE_GRID, 'min-w-[64rem]']">
							<div :class="[INVOICE_COLS, HEADER_CLASS]">
								<span>Invoice</span>
								<span>Customer</span>
								<span>Contact</span>
								<span>Due</span>
								<span class="text-right">Outstanding</span>
								<span>Age</span>
								<span>Last contact</span>
								<span />
							</div>
							<ReceivableInvoiceRow
								v-for="item in visibleItems"
								:key="item.voucher_no"
								:item="item"
								:currency="data.currency"
							/>
							<p v-if="!visibleItems.length" class="col-span-8 px-4 py-10 text-center text-sm text-ink-gray-5">
								{{ emptyText }}
							</p>
						</div>
					</div>

					<div class="flex flex-wrap justify-between gap-2 border-t border-outline-gray-2 px-4 py-2 text-xs text-ink-gray-6">
						<span>{{ footerText }}</span>
						<span>Sales invoices with an open amount, from the Accounts Receivable report. Last contact: sent email or dunning.</span>
					</div>
				</section>
			</template>
		</div>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Button, call } from "frappe-ui"
import HorizontalBars from "@spa/components/dashboard/HorizontalBars.vue"
import StatCard from "@spa/components/dashboard/StatCard.vue"
import { pluralize } from "@spa/utils/dashboardFormat.js"
import ReceivableCustomerRow from "../components/ReceivableCustomerRow.vue"
import ReceivableInvoiceRow from "../components/ReceivableInvoiceRow.vue"
import {
	CUSTOMER_COLS,
	CUSTOMER_GRID,
	DEFAULT_FILTERS,
	INVOICE_COLS,
	INVOICE_GRID,
	SORT_OPTIONS,
	customerMatches,
	groupInvoices,
	invoiceMatches,
	invoicePasses,
	sortCustomers,
	sortInvoices,
} from "../receivableColumns"
import { formatMoney } from "../statsFormat"

const API = "phamos.api.accounting_receivables.get_receivables"
const VIEWS = [
	{ value: "customers", label: "By customer" },
	{ value: "invoices", label: "Invoices" },
]
const HEADER_CLASS =
	"sticky top-0 z-10 border-b border-outline-gray-2 bg-surface-gray-1 px-4 py-2 text-xs font-medium uppercase tracking-wide text-ink-gray-5"

const route = useRoute()
const router = useRouter()
const search = ref(null)
const data = ref(null)
const loading = ref(false)
const error = ref("")
const expanded = ref(new Set())
let requestId = 0

// View, filters and sort live in the URL, so a link or bookmark opens the same view.
const filters = reactive({ ...DEFAULT_FILTERS, ...pickQuery(route.query) })

function pickQuery(query) {
	const out = {}
	for (const key of Object.keys(DEFAULT_FILTERS)) if (query[key]) out[key] = String(query[key])
	return out
}

watch(
	filters,
	() => {
		const query = Object.fromEntries(Object.entries(filters).filter(([key, value]) => value && value !== DEFAULT_FILTERS[key]))
		router.replace({ query })
	},
	{ deep: true }
)

const overdueOnly = computed({
	get: () => Boolean(filters.overdue),
	set: (value) => (filters.overdue = value ? "1" : ""),
})

const totals = computed(() => data.value?.totals || {})
const bucketLabel = computed(() => data.value?.buckets.find((b) => b.key === filters.bucket)?.label || filters.bucket)

function money(value) {
	return formatMoney(value, data.value?.currency)
}

// Items that pass search and toggles; a customer whose name matches keeps all its items.
const filteredItems = computed(() => {
	const items = data.value?.invoices || []
	const matchingCustomers = new Set(
		(data.value?.customers || []).filter((c) => filters.q && customerMatches(c, filters.q)).map((c) => c.customer)
	)
	return items.filter(
		(item) => invoicePasses(item, filters) && (matchingCustomers.has(item.customer) || invoiceMatches(item, filters.q))
	)
})

const visibleItems = computed(() => sortInvoices(filteredItems.value, filters.sort))
const itemsByCustomer = computed(() => groupInvoices(visibleItems.value))

const visibleCustomers = computed(() => {
	const customers = data.value?.customers || []
	const filtering = filters.q || filters.overdue || filters.bucket
	const shown = filtering ? customers.filter((c) => itemsByCustomer.value[c.customer]?.length) : customers
	return sortCustomers(shown, filters.sort)
})

// A search that matches an invoice but not its customer opens that customer.
const autoExpanded = computed(() => {
	if (!filters.q) return new Set()
	return new Set(visibleCustomers.value.filter((c) => !customerMatches(c, filters.q)).map((c) => c.customer))
})

function toggle(customer) {
	const next = new Set(expanded.value)
	if (next.has(customer)) next.delete(customer)
	else next.add(customer)
	expanded.value = next
}

const emptyText = computed(() =>
	(data.value?.invoices || []).length ? "Nothing matches these filters." : "Nothing outstanding."
)

const footerText = computed(() => {
	const items = visibleItems.value
	const sum = items.reduce((total, item) => total + item.outstanding, 0)
	const count = items.filter((item) => item.kind === "invoice").length
	const customers = filters.view === "customers" ? ` · ${pluralize(visibleCustomers.value.length, "customer", "customers")}` : ""
	return `${pluralize(count, "invoice", "invoices")}${customers} · ${money(sum)}`
})

// generated_at is server time "YYYY-MM-DD HH:MM:SS…"; the time is enough next to today's date.
const asOf = computed(() => String(data.value?.generated_at || "").slice(11, 16))

function selectBucket(row) {
	filters.bucket = filters.bucket === row.key ? "" : row.key
	filters.view = "invoices"
}

function selectCompany(company) {
	filters.company = company
	expanded.value = new Set()
	load()
}

function showOverdue() {
	filters.bucket = ""
	filters.overdue = "1"
}

async function load() {
	const id = ++requestId
	loading.value = true
	try {
		const result = await call(API, filters.company ? { company: filters.company } : {})
		if (id !== requestId) return
		data.value = result
		error.value = ""
	} catch (e) {
		if (id !== requestId) return
		error.value = e?.messages?.[0] || e?.message || "Could not load the receivables"
	} finally {
		if (id === requestId) loading.value = false
	}
}

function isTyping(event) {
	const target = event.target
	return target?.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName)
}

// "/" focuses the search, like in Desk lists.
function onKeydown(event) {
	if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || isTyping(event)) return
	if (event.key !== "/") return
	event.preventDefault()
	search.value?.focus()
}

onMounted(() => {
	load()
	window.addEventListener("keydown", onKeydown)
})
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown))
</script>
