<template>
	<ReceiptDropArea @changed="load" @open="open">
		<template #default="{ pick }">
			<div class="flex flex-wrap items-end gap-3 border-b border-outline-gray-2 bg-surface-white px-5 py-3 text-sm">
				<label class="filter">
					<span>Search</span>
					<input v-model="filters.search" type="search" placeholder="Supplier, number, title…" class="input w-56" @input="loadSoon" />
				</label>
				<label class="filter">
					<span>From</span>
					<input v-model="filters.from_date" type="date" class="input" @change="load" />
				</label>
				<label class="filter">
					<span>To</span>
					<input v-model="filters.to_date" type="date" class="input" @change="load" />
				</label>
				<label class="filter">
					<span>Status</span>
					<select v-model="filters.status" class="input" @change="load">
						<option value="">All</option>
						<option v-for="s in STATUSES" :key="s" :value="s">{{ s }}</option>
					</select>
				</label>
				<label class="filter">
					<span>Receipt type</span>
					<select v-model="filters.receipt_type" class="input" @change="load">
						<option value="">All</option>
						<option v-for="t in TYPES" :key="t" :value="t">{{ t }}</option>
					</select>
				</label>
				<label class="filter w-56">
					<span>Supplier</span>
					<FrappeLink v-model="filters.supplier" doctype="Supplier" placeholder="Any supplier" />
				</label>
				<label class="filter">
					<span>Sort</span>
					<select v-model="filters.sort" class="input" @change="load">
						<option value="posting_date">Date</option>
						<option value="due_date">Due date</option>
						<option value="sum_in_company_currency">Amount</option>
						<option value="modified">Last changed</option>
					</select>
				</label>
				<button type="button" class="btn" @click="toggleOrder">{{ filters.order === "desc" ? "↓ newest" : "↑ oldest" }}</button>
				<button v-if="hasFilters" type="button" class="text-xs text-ink-gray-6 hover:text-ink-gray-9" @click="reset">Reset</button>
				<button type="button" class="btn ml-auto" :disabled="fetching" @click="fetchEmails">
					{{ fetching ? "Fetching e-mails…" : "Fetch e-mails" }}
				</button>
				<button type="button" class="btn" @click="pick()">Upload</button>
			</div>
			<div class="min-h-0 flex-1 overflow-y-auto bg-surface-white">
				<p v-if="truncated" class="border-b border-outline-gray-2 bg-surface-amber-1 px-5 py-2 text-xs text-ink-amber-3">
					Showing the first {{ items.length }} receipts. Narrow the filters to see the rest.
				</p>
				<p v-if="error" class="px-5 py-10 text-center text-sm text-ink-red-4">{{ error }}</p>
				<p v-else-if="loading && !items.length" class="px-5 py-10 text-center text-sm text-ink-gray-5">Loading…</p>
				<p v-else-if="!items.length" class="px-5 py-10 text-center text-sm text-ink-gray-5">No receipts match these filters.</p>
				<ReceiptRow v-for="item in items" :key="item.name" :item="item" @open="open" />
			</div>
			<div class="border-t border-outline-gray-2 bg-surface-white px-5 py-2 text-xs text-ink-gray-6">
				{{ items.length }} receipt(s) · {{ sumText }}
			</div>
		</template>
	</ReceiptDropArea>
</template>

<script setup>
import { computed, getCurrentInstance, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call, debounce, toast } from "frappe-ui"
import FrappeLink from "@spa/components/FrappeLink.vue"
import ReceiptDropArea from "../components/ReceiptDropArea.vue"
import ReceiptRow from "../components/ReceiptRow.vue"
import { setReviewOrder } from "../reviewOrder"

const STATUSES = ["Inbox", "Needs Decision", "Approved to Pay", "Do Not Pay", "Sent to DATEV", "Paid", "Cancelled"]
const TYPES = ["Invoice", "Credit Note", "Receipt", "Tax Notice", "Contract", "Reminder", "Statement", "Other"]
const DEFAULTS = { search: "", from_date: "", to_date: "", status: "", receipt_type: "", supplier: "", sort: "posting_date", order: "desc" }

const route = useRoute()
const router = useRouter()
// Filters live in the URL, so statistics drill-downs and bookmarks open the same view.
const filters = reactive({ ...DEFAULTS, ...pickQuery(route.query) })
const items = ref([])
const truncated = ref(false)
const loading = ref(false)
const error = ref("")

const hasFilters = computed(() => Object.keys(DEFAULTS).some((k) => k !== "sort" && k !== "order" && filters[k]))
const sumText = computed(() => {
	const byCurrency = {}
	for (const item of items.value) byCurrency[item.currency || ""] = (byCurrency[item.currency || ""] || 0) + Number(item.sum || 0)
	return Object.entries(byCurrency)
		.map(([cur, sum]) => `${sum.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${cur}`)
		.join(" · ")
})

function pickQuery(query) {
	const out = {}
	for (const key of Object.keys(DEFAULTS)) if (query[key]) out[key] = String(query[key])
	if (query.from) out.from_date = String(query.from)
	if (query.to) out.to_date = String(query.to)
	return out
}

async function load({ quiet = false } = {}) {
	if (!quiet) loading.value = true
	const args = Object.fromEntries(Object.entries(filters).filter(([, v]) => v))
	router.replace({ query: Object.fromEntries(Object.entries(args).filter(([k, v]) => DEFAULTS[k] !== v)) })
	try {
		const res = await call("phamos.api.accounting_receipts.list_receipts", args)
		items.value = res.items || []
		truncated.value = Boolean(res.truncated)
		error.value = ""
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load receipts"
	} finally {
		loading.value = false
	}
}

const loadSoon = debounce(() => load(), 300)
watch(() => filters.supplier, () => load())

function toggleOrder() {
	filters.order = filters.order === "desc" ? "asc" : "desc"
	load()
}

function reset() {
	Object.assign(filters, DEFAULTS)
	load()
}

function open(name) {
	setReviewOrder(items.value.map((i) => i.name), "all")
	router.push({ name: "ReceiptDetail", params: { name } })
}

// "Fetch e-mails" (#1964): pull the receipt inboxes now. The server queues one background job
// per account and each job sends `receipt_emails_fetched` to this user when it is done.
const FETCH_EVENT = "receipt_emails_fetched"
const socket = getCurrentInstance()?.appContext?.config?.globalProperties?.$socket || null
const fetching = ref(false)
let pending = 0
let fallbackTimer = null

async function fetchEmails() {
	fetching.value = true
	try {
		const res = await call("phamos.accounting.email_pull.fetch_receipt_emails")
		pending = res.queued.length
		if (!pending) {
			toast({ title: "E-mails are already being fetched", icon: "clock" })
			fetching.value = false
			return
		}
		toast({ title: "Fetching e-mails…", icon: "download" })
		// Without realtime, or if an event gets lost, nobody tells us the job is done: give the
		// button back and reload after a while in any case.
		clearTimeout(fallbackTimer)
		fallbackTimer = setTimeout(finishFetch, socket?.connected ? 60000 : 20000)
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "Could not fetch e-mails", icon: "x-circle", iconClasses: "text-ink-red-4" })
		fetching.value = false
	}
}

function onFetched(data) {
	if (data.error) toast({ title: data.error, icon: "x-circle", iconClasses: "text-ink-red-4" })
	else if (data.created) toast({ title: `${data.created} new receipt(s) from e-mail`, icon: "check-circle", iconClasses: "text-ink-green-3" })
	else toast({ title: "No new e-mails", icon: "check-circle" })
	pending = Math.max(pending - 1, 0)
	if (!pending) finishFetch()
	else load({ quiet: true })
}

function finishFetch() {
	clearTimeout(fallbackTimer)
	fetching.value = false
	load({ quiet: true })
}

onMounted(() => {
	load()
	socket?.on(FETCH_EVENT, onFetched)
})
onBeforeUnmount(() => {
	socket?.off(FETCH_EVENT, onFetched)
	clearTimeout(fallbackTimer)
})
</script>

<style scoped>
.filter {
	@apply flex flex-col gap-1;
}
.filter > span {
	@apply text-xs text-ink-gray-5;
}
.input {
	@apply h-8 rounded-md border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-9;
}
.btn {
	@apply inline-flex h-8 items-center rounded-md border border-outline-gray-2 px-3 text-sm font-medium text-ink-gray-8 hover:bg-surface-gray-2 disabled:cursor-wait disabled:opacity-60;
}
</style>
