<template>
	<div class="flex h-full min-h-0">
		<section
			class="flex min-w-0 flex-col border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
			:class="selectedName ? 'w-[15%] flex-none' : 'flex-1'"
		>
			<div
				class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-5 py-3 dark:border-gray-800"
			>
				<div class="text-sm text-gray-600 dark:text-gray-400">
					{{ filteredReceipts.length }} receipt{{ filteredReceipts.length === 1 ? "" : "s" }}
				</div>
				<div v-if="!selectedName" class="flex items-center gap-3">
					<input
						v-model="search"
						type="search"
						placeholder="Search…"
						class="h-8 w-44 rounded-md border border-gray-300 bg-white px-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
					/>
					<a
						href="/app/accounting-receipt/new"
						class="inline-flex h-8 items-center rounded-md bg-gray-900 px-3 text-sm font-medium text-white hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-white"
					>
						New Receipt
					</a>
				</div>
			</div>

			<div
				v-if="configError"
				class="flex flex-1 items-center justify-center px-6 text-center text-sm text-red-600 dark:text-red-400"
			>
				{{ configError }}
			</div>
			<div v-else-if="loading" class="flex flex-1 items-center justify-center text-sm text-gray-500 dark:text-gray-400">
				Loading…
			</div>
			<template v-else-if="!filteredReceipts.length">
				<div class="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
					<p class="font-medium text-gray-900 dark:text-gray-100">No accounting receipts</p>
					<p class="max-w-sm text-sm text-gray-500 dark:text-gray-400">
						Incoming receipts will appear on this board once created or emailed in.
					</p>
				</div>
			</template>
			<ReceiptKanban
				v-else
				:receipts="filteredReceipts"
				:selected-name="selectedName"
				@select="openReceipt"
				@status-change="onKanbanStatusChange"
			/>
		</section>

		<aside
			v-if="selectedName"
			class="flex w-[85%] min-w-0 flex-none flex-col overflow-hidden bg-white dark:bg-gray-900"
		>
			<div
				v-if="detailLoading && !selectedReceipt"
				class="flex flex-1 items-center justify-center text-sm text-gray-500 dark:text-gray-400"
			>
				Loading…
			</div>
			<ReceiptDetailPanel
				v-else-if="selectedReceipt"
				:receipt="selectedReceipt"
				:extract-status="extractStatus"
				:extract-updated-count="extractUpdatedCount"
				:extract-error-message="extractErrorMessage"
				@close="closeReceipt"
				@review-correct="onReviewCorrect"
			/>
		</aside>

		<ReceiptExtractReviewDialog
			v-if="reviewState"
			v-model="showReview"
			:receipt-name="reviewState.receiptName"
			:fields="reviewState.fields"
			:extracted="reviewState.extracted"
			:attachment-url="reviewState.attachmentUrl"
			@applied="onReviewApplied"
		/>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call, toast } from "frappe-ui"
import ReceiptDetailPanel from "../components/ReceiptDetailPanel.vue"
import ReceiptExtractReviewDialog from "../components/ReceiptExtractReviewDialog.vue"
import ReceiptKanban from "../components/ReceiptKanban.vue"

const API = "phamos.api.accounting_spa"
const POLL_INTERVAL_MS = 2000
const POLL_MAX_MS = 120000

const route = useRoute()
const router = useRouter()

const search = ref("")
const loading = ref(false)
const configError = ref("")
const receipts = ref([])
const selectedName = ref(null)
const selectedReceipt = ref(null)
const detailLoading = ref(false)
const extractStatus = ref("idle")
const extractUpdatedCount = ref(0)
const extractErrorMessage = ref("")
const showReview = ref(false)
const reviewState = ref(null)

let pollTimer = null
let pollStartedAt = 0

const filteredReceipts = computed(() => {
	const q = search.value.trim().toLowerCase()
	if (!q) return receipts.value
	return receipts.value.filter((r) =>
		[r.name, r.title, r.supplier_reference, r.supplier_name, r.supplier, r.status]
			.filter(Boolean)
			.some((v) => String(v).toLowerCase().includes(q))
	)
})

function stopExtractPolling() {
	if (pollTimer) {
		clearInterval(pollTimer)
		pollTimer = null
	}
}

function formatExtractFailure(status) {
	if (status?.reason === "mistral_not_configured") {
		return "Mistral is not configured in phamos Settings."
	}
	if (status?.reason === "no_attachment") {
		return "PDF attachment is missing."
	}
	if (status?.reason === "pdf_not_found") {
		return "PDF file could not be found on disk."
	}
	return status?.message || status?.reason || "PDF extraction failed."
}

async function pollExtractStatus(name) {
	try {
		const status = await call(`${API}.get_receipt_extract_status`, { name })
		applyExtractStatus(status)

		if (status.status === "done" || status.status === "failed") {
			stopExtractPolling()
			await loadReceipts()
			if (selectedName.value === name) {
				await refreshSelectedReceipt()
			}
			if (status.status === "failed") {
				toast.error(formatExtractFailure(status))
			}
		} else if (Date.now() - pollStartedAt > POLL_MAX_MS) {
			stopExtractPolling()
			extractStatus.value = "failed"
			extractErrorMessage.value = "Extraction timed out."
			toast.error("PDF extraction timed out.")
		}
	} catch (e) {
		stopExtractPolling()
		extractStatus.value = "failed"
		extractErrorMessage.value = e?.messages?.[0] || e?.message || "Could not check extraction status"
	}
}

function applyExtractStatus(status) {
	const s = status?.status || "idle"
	extractStatus.value = s
	if (s === "done") {
		extractUpdatedCount.value = (status.updated || []).length
		extractErrorMessage.value = ""
	} else if (s === "failed") {
		extractErrorMessage.value = formatExtractFailure(status)
	} else {
		extractUpdatedCount.value = 0
		if (s !== "running") extractErrorMessage.value = ""
	}
}

function startExtractPolling(name) {
	stopExtractPolling()
	pollStartedAt = Date.now()
	pollTimer = setInterval(() => pollExtractStatus(name), POLL_INTERVAL_MS)
}

async function startBackgroundExtract(receipt) {
	if (!receipt?.has_pdf) {
		extractStatus.value = "idle"
		extractUpdatedCount.value = 0
		extractErrorMessage.value = ""
		return
	}

	const current = await call(`${API}.get_receipt_extract_status`, { name: receipt.name })
	applyExtractStatus(current)
	if (current.status === "running") {
		startExtractPolling(receipt.name)
		return
	}

	const res = await call(`${API}.enqueue_receipt_pdf_extract`, { name: receipt.name })
	if (res?.queued) {
		extractStatus.value = "running"
		startExtractPolling(receipt.name)
		return
	}

	if (res?.reason === "already_running") {
		extractStatus.value = "running"
		startExtractPolling(receipt.name)
		return
	}

	if (res?.reason === "no_attachment") {
		extractStatus.value = "idle"
	}
}

async function loadReceipts() {
	loading.value = true
	configError.value = ""
	try {
		receipts.value = await call(`${API}.get_receipts`)
	} catch (e) {
		configError.value = e?.messages?.[0] || e?.message || "Could not load receipts"
	} finally {
		loading.value = false
	}
}

async function openReceipt(name) {
	stopExtractPolling()
	selectedName.value = name
	extractStatus.value = "idle"
	extractUpdatedCount.value = 0
	extractErrorMessage.value = ""

	if (route.params.name !== name) {
		router.replace({ name: "ReceiptDetail", params: { name } })
	}
	detailLoading.value = true
	try {
		selectedReceipt.value = await call(`${API}.get_receipt`, { name })
		await startBackgroundExtract(selectedReceipt.value)
	} finally {
		detailLoading.value = false
	}
}

function closeReceipt() {
	stopExtractPolling()
	selectedName.value = null
	selectedReceipt.value = null
	showReview.value = false
	reviewState.value = null
	extractStatus.value = "idle"
	router.replace({ name: "Receipts" })
}

async function refreshSelectedReceipt() {
	if (!selectedName.value) return
	selectedReceipt.value = await call(`${API}.get_receipt`, { name: selectedName.value })
}

async function onKanbanStatusChange({ name, status }) {
	try {
		const updated = await call(`${API}.update_receipt_status`, { name, status })
		await loadReceipts()
		if (selectedName.value === name) selectedReceipt.value = updated
	} catch (e) {
		await loadReceipts()
	}
}

async function onReviewCorrect() {
	if (!selectedReceipt.value?.name || !selectedReceipt.value?.has_pdf) return
	try {
		const res = await call(`${API}.get_receipt_review_fields`, { name: selectedReceipt.value.name })
		if (!res?.ok || !res.fields?.length) {
			toast.info("No fields available for review.")
			return
		}
		reviewState.value = {
			receiptName: selectedReceipt.value.name,
			fields: res.fields,
			extracted: res.extracted || {},
			attachmentUrl: selectedReceipt.value.attachment || "",
		}
		showReview.value = true
	} catch (e) {
		toast.error(e?.messages?.[0] || e?.message || "Could not load review fields")
	}
}

async function onReviewApplied() {
	await loadReceipts()
	await refreshSelectedReceipt()
}

watch(showReview, (open) => {
	if (!open) reviewState.value = null
})

watch(
	() => route.params.name,
	(name) => {
		if (name && name !== selectedName.value) openReceipt(name)
		if (!name) {
			stopExtractPolling()
			selectedName.value = null
			selectedReceipt.value = null
			showReview.value = false
			reviewState.value = null
		}
	}
)

onBeforeUnmount(() => {
	stopExtractPolling()
})

onMounted(async () => {
	await loadReceipts()
	if (route.params.name) await openReceipt(route.params.name)
})
</script>
