<template>
	<div class="flex h-full min-h-0">
		<section
			class="relative flex min-w-0 flex-col border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
			:class="selectedName ? 'w-[15%] flex-none' : 'flex-1'"
			@dragenter="onDragEnter"
			@dragover="onDragOver"
			@dragleave="onDragLeave"
			@drop="onDropFiles"
		>
			<div
				v-if="dropActive"
				class="pointer-events-none absolute inset-2 z-20 flex flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-ink-blue-3 bg-surface-white/90 text-center"
			>
				<p class="text-base font-semibold text-ink-gray-9">Drop PDFs or e-mails to create receipts</p>
				<p class="text-sm text-ink-gray-6">One receipt per PDF. E-mails without a PDF get one made from the mail text.</p>
			</div>
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
					<button
						type="button"
						class="inline-flex h-8 items-center rounded-md border border-gray-300 px-3 text-sm font-medium text-gray-800 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800"
						@click="fileInput?.click()"
					>
						Upload
					</button>
					<input
						ref="fileInput"
						type="file"
						multiple
						accept=".pdf,.eml,application/pdf,message/rfc822"
						class="hidden"
						@change="onPickFiles"
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
				v-if="dropNotice"
				class="flex items-start justify-between gap-3 border-b border-outline-gray-2 bg-surface-amber-1 px-5 py-2 text-sm text-ink-amber-3"
			>
				<span>{{ dropNotice }}</span>
				<button type="button" class="text-xs text-ink-gray-5 hover:text-ink-gray-8" @click="dropNotice = ''">Close</button>
			</div>
			<ReceiptUploadList :uploads="uploads" @open="openReceipt" @force="forceUpload" @clear="uploads = []" />
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
						Drop PDFs or e-mails here, or use Upload.
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
				@run-extract="runExtract(false)"
				@rerun-extract="runExtract(true)"
				@send-to-datev="sendToDatev"
				@save-note="saveNote"
				@preview-datev="previewDatev"
			/>
		</aside>

		<ExtractDiffDialog
			v-if="selectedReceipt"
			v-model="showReview"
			:receipt-name="selectedReceipt.name"
			:attachment-url="selectedReceipt.attachment || ''"
			@applied="onReviewApplied"
		/>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call, toast } from "frappe-ui"
import ReceiptDetailPanel from "../components/ReceiptDetailPanel.vue"
import ExtractDiffDialog from "../components/ExtractDiffDialog.vue"
import ReceiptKanban from "../components/ReceiptKanban.vue"
import ReceiptUploadList from "../components/ReceiptUploadList.vue"
import { droppedFiles, droppedMailLink, isExternalDrag, isReceiptFile, uploadReceiptFile } from "../receiptUpload"

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

const fileInput = ref(null)
const dropActive = ref(false)
const dropNotice = ref("")
const uploads = ref([])
let dragDepth = 0
let uploadSeq = 0
let refreshTimer = null

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
				toast({
					title: formatExtractFailure(status),
					icon: "x-circle",
					iconClasses: "text-ink-red-4",
				})
			}
		} else if (Date.now() - pollStartedAt > POLL_MAX_MS) {
			stopExtractPolling()
			extractStatus.value = "failed"
			extractErrorMessage.value = "Extraction timed out."
			toast({
				title: "PDF extraction timed out.",
				icon: "x-circle",
				iconClasses: "text-ink-red-4",
			})
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

async function showExtractState(receipt) {
	// Opening a receipt only shows the extraction state; it never starts a new run,
	// because a run overwrites the values a human may have corrected.
	if (!receipt?.has_pdf) {
		applyExtractStatus({ status: "idle" })
		return
	}
	const current = await call(`${API}.get_receipt_extract_status`, { name: receipt.name })
	applyExtractStatus(current)
	if (current.status === "running") startExtractPolling(receipt.name)
}

async function runExtract(overwrite = false) {
	const receipt = selectedReceipt.value
	if (!receipt?.has_pdf) return
	if (overwrite && !window.confirm("Read the PDF again and replace the values on this receipt with what the AI reads?")) return
	try {
		const res = await call(`${API}.enqueue_receipt_pdf_extract`, { name: receipt.name, overwrite: overwrite ? 1 : 0 })
		if (res?.queued || res?.reason === "already_running") {
			extractStatus.value = "running"
			startExtractPolling(receipt.name)
		}
	} catch (e) {
		toast({
			title: e?.messages?.[0] || e?.message || "Could not start the extraction",
			icon: "x-circle",
			iconClasses: "text-ink-red-4",
		})
	}
}

async function sendToDatev() {
	if (pendingNoteSave) await pendingNoteSave
	const receipt = selectedReceipt.value
	if (!receipt) return
	const info = await call("phamos.phamos.doctype.accounting_receipt.accounting_receipt.get_datev_send_info", {
		accounting_receipt_name: receipt.name,
	})
	if (!info?.ok || !info.recipient || !info.pdf_url) {
		toast({
			title: info?.message || (!info?.recipient ? "No DATEV recipient is configured." : "PDF attachment is missing."),
			icon: "x-circle",
			iconClasses: "text-ink-red-4",
		})
		return
	}
	const question = info.already_sent
		? `Already sent on ${info.sent_at} by ${info.sent_by}. Send ${info.pdf_name} to ${info.recipient} again?`
		: `Send ${info.pdf_name} to ${info.recipient}?`
	if (!window.confirm(question)) return
	const res = await call("phamos.phamos.doctype.accounting_receipt.accounting_receipt.send_to_datev", {
		accounting_receipt_name: receipt.name,
	})
	toast({
		title: res?.message || (res?.ok ? "Queued for DATEV." : "Sending failed."),
		icon: res?.ok ? "check-circle" : "x-circle",
		iconClasses: res?.ok ? "text-ink-green-3" : "text-ink-red-4",
	})
	await loadReceipts()
	await refreshSelectedReceipt()
}

function failToast(title) {
	toast({ title, icon: "x-circle", iconClasses: "text-ink-red-4" })
}

function onDragEnter(event) {
	if (!isExternalDrag(event)) return
	event.preventDefault()
	dragDepth += 1
	dropActive.value = true
}

function onDragOver(event) {
	if (!isExternalDrag(event)) return
	event.preventDefault()
	event.dataTransfer.dropEffect = "copy"
}

function onDragLeave(event) {
	if (!isExternalDrag(event)) return
	dragDepth = Math.max(0, dragDepth - 1)
	if (!dragDepth) dropActive.value = false
}

function onDropFiles(event) {
	if (!isExternalDrag(event)) return
	event.preventDefault()
	dragDepth = 0
	dropActive.value = false
	dropNotice.value = ""
	const files = droppedFiles(event)
	if (!files.length) {
		const types = Array.from(event.dataTransfer?.types || []).join(", ") || "nothing"
		dropNotice.value = droppedMailLink(event)
			? "Apple Mail handed over only a link to the message, not the mail itself. Drag the mail (or its PDF) to the Desktop first, then drop that file here."
			: `The drop contained no file the browser can read (received: ${types}). Drag the file from Finder or the Desktop, or use Upload.`
		return
	}
	startUploads(files)
}

function onPickFiles(event) {
	startUploads(Array.from(event.target.files || []))
	event.target.value = ""
}

function startUploads(files) {
	const accepted = files.filter(isReceiptFile)
	const rejected = files.filter((file) => !isReceiptFile(file)).map((file) => file.name)
	if (rejected.length) {
		dropNotice.value = `Skipped ${rejected.join(", ")}: only PDFs and e-mails (.eml) create receipts.`
	}
	for (const file of accepted) runUpload(file, false)
}

async function runUpload(file, allowDuplicate, existing = null) {
	const upload = existing || { id: ++uploadSeq, filename: file.name, file }
	Object.assign(upload, { state: "uploading", results: [], error: "" })
	if (!existing) uploads.value = [...uploads.value, upload]
	try {
		upload.results = await uploadReceiptFile(file, { allowDuplicate })
		upload.state = "done"
	} catch (e) {
		upload.state = "error"
		upload.error = e?.message || "Upload failed"
	}
	uploads.value = [...uploads.value]
	await loadReceipts()
	scheduleRefreshForAi()
}

function forceUpload(upload) {
	runUpload(upload.file, true, upload)
}

// New receipts are read by the AI in the background; refresh the board a few times so
// the extracted values appear without reloading the page.
function scheduleRefreshForAi() {
	if (refreshTimer) clearInterval(refreshTimer)
	let rounds = 0
	refreshTimer = setInterval(async () => {
		rounds += 1
		await loadReceipts({ quiet: true })
		if (selectedName.value) await refreshSelectedReceipt()
		if (rounds >= 10) {
			clearInterval(refreshTimer)
			refreshTimer = null
		}
	}, 3000)
}

// Leaving the note field (e.g. by clicking Send to DATEV) saves it; send and preview wait
// for that save so the PDF always carries the note as typed.
let pendingNoteSave = null

function saveNote(text) {
	pendingNoteSave = persistNote(text).finally(() => {
		pendingNoteSave = null
	})
	return pendingNoteSave
}

async function persistNote(text) {
	const receipt = selectedReceipt.value
	if (!receipt) return
	try {
		const res = await call("phamos.api.accounting_receipts.update_receipt_note", { name: receipt.name, note: text })
		selectedReceipt.value = { ...receipt, note_text: res.note_text }
		toast({ title: "Note saved", icon: "check-circle", iconClasses: "text-ink-green-3" })
	} catch (e) {
		failToast(e?.messages?.[0] || e?.message || "Could not save the note")
	}
}

async function previewDatev() {
	if (pendingNoteSave) await pendingNoteSave
	const receipt = selectedReceipt.value
	if (!receipt) return
	try {
		const res = await call("phamos.phamos.doctype.accounting_receipt.accounting_receipt.preview_datev_pdf", {
			accounting_receipt_name: receipt.name,
		})
		if (res?.file_url) window.open(res.file_url, "_blank")
	} catch (e) {
		failToast(e?.messages?.[0] || e?.message || "Could not build the DATEV PDF")
	}
}

async function loadReceipts({ quiet = false } = {}) {
	if (!quiet) loading.value = true
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
		await showExtractState(selectedReceipt.value)
	} finally {
		detailLoading.value = false
	}
}

function closeReceipt() {
	stopExtractPolling()
	selectedName.value = null
	selectedReceipt.value = null
	showReview.value = false
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
		toast({
			title: e?.messages?.[0] || e?.message || "Could not move the receipt",
			icon: "x-circle",
			iconClasses: "text-ink-red-4",
		})
		await loadReceipts()
	}
}

function onReviewCorrect() {
	if (selectedReceipt.value?.name) showReview.value = true
}

async function onReviewApplied() {
	await loadReceipts()
	await refreshSelectedReceipt()
}


watch(
	() => route.params.name,
	(name) => {
		if (name && name !== selectedName.value) openReceipt(name)
		if (!name) {
			stopExtractPolling()
			selectedName.value = null
			selectedReceipt.value = null
			showReview.value = false
		}
	}
)

onBeforeUnmount(() => {
	stopExtractPolling()
	if (refreshTimer) clearInterval(refreshTimer)
})

onMounted(async () => {
	await loadReceipts()
	if (route.params.name) await openReceipt(route.params.name)
})
</script>
