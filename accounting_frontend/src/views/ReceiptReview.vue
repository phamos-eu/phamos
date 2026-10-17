<template>
	<div class="flex h-full min-h-0 flex-col bg-surface-white">
		<!-- Review bar: where am I, what do I decide -->
		<div class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 px-5 py-2">
			<button type="button" class="btn" title="Back (Esc)" @click="back">← {{ origin === "all" ? "All receipts" : "Queue" }}</button>
			<span v-if="position.index >= 0" class="text-xs text-ink-gray-6">{{ position.index + 1 }} of {{ order.length }}</span>
			<button type="button" class="btn" :disabled="!position.previous" title="Previous (k)" @click="go(position.previous)">‹</button>
			<button type="button" class="btn" :disabled="!position.next" title="Skip to next (j)" @click="go(position.next)">Skip ›</button>
			<div class="ml-auto flex flex-wrap items-center gap-2">
				<button type="button" class="btn" :disabled="!canApprove || busy" :title="approveHint" @click="approve">
					Approve to pay
				</button>
				<button type="button" class="btn" :disabled="!detail.receipt.value || busy" title="Already paid, e.g. by card or direct debit (p)" @click="openPaid">
					Already paid
				</button>
				<button type="button" class="btn" :disabled="!detail.receipt.value || busy" title="Don't pay (x)" @click="decide('Do Not Pay', 'Marked: do not pay')">
					Don't pay
				</button>
				<button type="button" class="btn-primary" :disabled="!detail.receipt.value?.has_pdf || busy" title="Send to DATEV (d)" @click="sendAndNext">
					Send to DATEV
				</button>
			</div>
		</div>

		<div v-if="detail.loading.value && !detail.receipt.value" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">Loading…</div>
		<div v-else-if="!detail.receipt.value" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">Receipt not found.</div>
		<ReceiptDetailPanel
			v-else
			ref="panel"
			:receipt="detail.receipt.value"
			:extract-status="detail.extractStatus.value"
			:extract-updated-count="detail.extractUpdatedCount.value"
			:extract-error-message="detail.extractErrorMessage.value"
			@close="back"
			@updated="detail.setReceipt"
			@review-correct="detail.showCompare.value = true"
			@run-extract="detail.runExtract(false)"
			@rerun-extract="detail.runExtract(true)"
			@send-to-datev="detail.sendToDatev"
			@save-note="detail.saveNote"
			@preview-datev="detail.previewDatev"
		/>
		<ExtractDiffDialog
			v-if="detail.receipt.value"
			v-model="detail.showCompare.value"
			:receipt-name="detail.receipt.value.name"
			:attachment-url="detail.receipt.value.attachment || ''"
			@applied="detail.refresh"
		/>
		<ApproveDialog v-if="detail.receipt.value && showApprove" v-model="showApprove" :receipt="detail.receipt.value" @approved="onApproved" />
		<PaidDialog v-if="detail.receipt.value && showPaid" v-model="showPaid" :receipt="detail.receipt.value" @paid="onPaid" />
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { call, toast } from "frappe-ui"
import ApproveDialog from "../components/ApproveDialog.vue"
import ExtractDiffDialog from "../components/ExtractDiffDialog.vue"
import PaidDialog from "../components/PaidDialog.vue"
import ReceiptDetailPanel from "../components/ReceiptDetailPanel.vue"
import { useReceiptDetail } from "../composables/useReceiptDetail"
import { getReviewOrder, neighbours, setReviewOrder } from "../reviewOrder"

const props = defineProps({ name: { type: String, required: true } })
const router = useRouter()
const detail = useReceiptDetail()
const panel = ref(null)
const busy = ref(false)

const stored = getReviewOrder()
const order = ref(stored?.names || [])
const origin = ref(stored?.origin || "queue")
const position = computed(() => neighbours(order.value, props.name))

async function ensureOrder() {
	// Opened directly (bookmark, link): walk the queue.
	if (order.value.length) return
	try {
		const res = await call("phamos.api.accounting_receipts.get_receipt_queue")
		order.value = (res.sections || [])
			.filter((s) => s.key === "decide" || s.key === "ready")
			.flatMap((s) => s.items.map((i) => i.name))
		origin.value = "queue"
		setReviewOrder(order.value, "queue")
	} catch (e) {
		order.value = []
	}
}

function go(name) {
	if (name) router.push({ name: "ReceiptDetail", params: { name } })
}

function back() {
	router.push({ name: origin.value === "all" ? "ReceiptsAll" : "Receipts" })
}

async function flushEdits() {
	await panel.value?.flush?.()
}

async function next() {
	const target = position.value.next
	if (target) go(target)
	else back()
}

// Approving to pay needs a submitted Purchase Invoice; the server enforces the same rule.
const canApprove = computed(() => detail.receipt.value?.purchase_invoice_docstatus === 1)
const approveHint = computed(() => {
	const receipt = detail.receipt.value
	if (canApprove.value) return "Approve to pay (a)"
	if (receipt?.purchase_invoice) return "Submit the Purchase Invoice first"
	return "Create and submit the Purchase Invoice first"
})

const showApprove = ref(false)

async function approve() {
	if (!canApprove.value) {
		toast({ title: approveHint.value, icon: "alert-triangle", iconClasses: "text-ink-amber-3" })
		return
	}
	await flushEdits()
	showApprove.value = true
}

async function onApproved(res) {
	detail.setReceipt(res.receipt)
	toast({
		title: res.payment_request ? `Approved · Payment Request ${res.payment_request}` : "Approved to pay",
		icon: "check-circle",
		iconClasses: "text-ink-green-3",
	})
	await next()
}

const showPaid = ref(false)

async function openPaid() {
	if (!detail.receipt.value) return
	await flushEdits()
	showPaid.value = true
}

async function onPaid(res) {
	detail.setReceipt(res.receipt)
	toast({
		title: res.cancelled_payment_request ? `Marked as paid · Payment Request ${res.cancelled_payment_request} cancelled` : "Marked as paid",
		icon: "check-circle",
		iconClasses: "text-ink-green-3",
	})
	await next()
}

async function decide(status, label) {
	busy.value = true
	try {
		await flushEdits()
		if (await detail.setStatus(status, label)) await next()
	} finally {
		busy.value = false
	}
}

async function sendAndNext() {
	busy.value = true
	try {
		await flushEdits()
		if (await detail.sendToDatev()) await next()
	} finally {
		busy.value = false
	}
}

function typing(event) {
	const el = event.target
	return el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || el.closest?.("[role=dialog]"))
}

function onKey(event) {
	if (event.metaKey || event.ctrlKey || event.altKey) return
	if (event.key === "Escape" && !typing(event)) return back()
	if (typing(event) || busy.value) return
	const actions = {
		j: () => go(position.value.next),
		k: () => go(position.value.previous),
		a: approve,
		p: openPaid,
		x: () => decide("Do Not Pay", "Marked: do not pay"),
		d: () => sendAndNext(),
	}
	const action = actions[event.key]
	if (action) {
		event.preventDefault()
		action()
	}
}

watch(() => props.name, (name) => detail.load(name), { immediate: true })
onMounted(() => {
	ensureOrder()
	window.addEventListener("keydown", onKey)
})
onBeforeUnmount(() => {
	window.removeEventListener("keydown", onKey)
	detail.stopPolling()
})
</script>

<style scoped>
.btn {
	@apply inline-flex h-8 items-center rounded-md border border-outline-gray-2 px-3 text-sm font-medium text-ink-gray-8 hover:bg-surface-gray-2 disabled:cursor-not-allowed disabled:opacity-40;
}
.btn-primary {
	@apply inline-flex h-8 items-center rounded-md bg-surface-gray-7 px-3 text-sm font-medium text-ink-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40;
}
</style>
