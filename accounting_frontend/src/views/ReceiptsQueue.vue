<template>
	<ReceiptDropArea @changed="load" @open="open">
		<template #default="{ pick }">
			<div class="flex flex-wrap items-center justify-between gap-3 border-b border-outline-gray-2 bg-surface-white px-5 py-3">
				<div class="text-sm text-ink-gray-7">
					<span class="font-semibold text-ink-gray-9">{{ counts.decide || 0 }}</span> to decide ·
					<span class="font-semibold text-ink-gray-9">{{ counts.ready || 0 }}</span> ready to send ·
					<span class="font-semibold text-ink-gray-9">{{ counts.waiting || 0 }}</span> waiting for payment
					<span v-if="overdue" class="font-semibold text-ink-red-4"> · {{ overdue }} overdue</span>
				</div>
				<div class="flex items-center gap-2">
					<button type="button" class="btn" @click="pick()">Upload</button>
					<button type="button" class="btn-primary" :disabled="!reviewOrder.length" @click="startReview">
						Start review
					</button>
				</div>
			</div>

			<div class="min-h-0 flex-1 overflow-y-auto bg-surface-white">
				<p v-if="error" class="px-5 py-10 text-center text-sm text-ink-red-4">{{ error }}</p>
				<p v-else-if="loading && !sections.length" class="px-5 py-10 text-center text-sm text-ink-gray-5">Loading…</p>
				<p v-else-if="!total" class="px-5 py-16 text-center text-sm text-ink-gray-6">
					Nothing to do. Drop PDFs or e-mails here, or use Upload.
				</p>
				<template v-for="section in sections" :key="section.key">
					<section v-if="section.items.length">
						<header class="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-outline-gray-2 bg-surface-gray-1 px-5 py-2">
							<div class="flex items-center gap-2">
								<input
									v-if="section.key === 'ready'"
									type="checkbox"
									class="rounded"
									:checked="allReadySelected"
									:title="allReadySelected ? 'Clear selection' : 'Select all'"
									@change="toggleAllReady"
								/>
								<h2 class="text-xs font-semibold uppercase tracking-wide text-ink-gray-7">{{ section.title }}</h2>
								<span class="rounded-full bg-surface-white px-1.5 text-[11px] text-ink-gray-6">{{ section.count }}</span>
							</div>
							<button
								v-if="section.key === 'ready' && selected.size"
								type="button"
								class="btn-primary"
								:disabled="sending"
								@click="sendSelected"
							>
								{{ sending ? "Sending…" : `Send ${selected.size} to DATEV` }}
							</button>
						</header>
						<div v-for="item in section.items" :key="item.name" class="flex items-center">
							<label v-if="section.key === 'ready'" class="flex-none pl-5" @click.stop>
								<input type="checkbox" class="rounded" :checked="selected.has(item.name)" @change="toggle(item.name)" />
							</label>
							<ReceiptRow class="flex-1" :item="item" @open="open" />
						</div>
					</section>
				</template>
			</div>
		</template>
	</ReceiptDropArea>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { call } from "frappe-ui"
import ReceiptDropArea from "../components/ReceiptDropArea.vue"
import ReceiptRow from "../components/ReceiptRow.vue"
import { failToast, okToast } from "../composables/useReceiptDetail"
import { setReviewOrder } from "../reviewOrder"

const API = "phamos.api.accounting_receipts"
const router = useRouter()

const sections = ref([])
const counts = ref({})
const overdue = ref(0)
const loading = ref(false)
const error = ref("")
const selected = ref(new Set())
const sending = ref(false)

const total = computed(() => sections.value.reduce((sum, s) => sum + s.items.length, 0))
// Review walks through what needs a human first, then what is ready to send.
const reviewOrder = computed(() =>
	sections.value.filter((s) => s.key === "decide" || s.key === "ready").flatMap((s) => s.items.map((i) => i.name))
)
const readyNames = computed(() => sections.value.find((s) => s.key === "ready")?.items.map((i) => i.name) || [])
const allReadySelected = computed(() => readyNames.value.length > 0 && readyNames.value.every((n) => selected.value.has(n)))

async function load({ quiet = false } = {}) {
	if (!quiet) loading.value = true
	try {
		const res = await call(`${API}.get_receipt_queue`)
		sections.value = res.sections || []
		counts.value = res.counts || {}
		overdue.value = res.overdue || 0
		error.value = ""
		selected.value = new Set([...selected.value].filter((n) => readyNames.value.includes(n)))
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load the queue"
	} finally {
		loading.value = false
	}
}

function allNames() {
	return sections.value.flatMap((s) => s.items.map((i) => i.name))
}

function open(name) {
	setReviewOrder(allNames(), "queue")
	router.push({ name: "ReceiptDetail", params: { name } })
}

function startReview() {
	setReviewOrder(reviewOrder.value, "queue")
	router.push({ name: "ReceiptDetail", params: { name: reviewOrder.value[0] } })
}

function toggle(name) {
	const next = new Set(selected.value)
	next.has(name) ? next.delete(name) : next.add(name)
	selected.value = next
}

function toggleAllReady() {
	selected.value = allReadySelected.value ? new Set() : new Set(readyNames.value)
}

async function sendSelected() {
	const names = [...selected.value]
	if (!window.confirm(`Send ${names.length} receipt(s) to DATEV?`)) return
	sending.value = true
	try {
		const res = await call(`${API}.send_receipts_to_datev`, { names })
		if (res.sent?.length) okToast(`${res.sent.length} sent to DATEV`)
		for (const f of res.failed || []) failToast(`${f.name}: ${f.message}`)
		selected.value = new Set()
		await load({ quiet: true })
	} catch (e) {
		failToast(e?.messages?.[0] || e?.message || "Sending failed")
	} finally {
		sending.value = false
	}
}

onMounted(load)
</script>

<style scoped>
.btn {
	@apply inline-flex h-8 items-center rounded-md border border-outline-gray-2 px-3 text-sm font-medium text-ink-gray-8 hover:bg-surface-gray-2;
}
.btn-primary {
	@apply inline-flex h-8 items-center rounded-md bg-surface-gray-7 px-3 text-sm font-medium text-ink-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40;
}
</style>
