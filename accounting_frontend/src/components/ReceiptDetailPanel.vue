<template>
	<div class="flex min-h-0 flex-1 flex-col lg:flex-row">
		<div class="flex min-w-0 flex-col gap-4 overflow-y-auto border-b border-gray-200 p-5 dark:border-gray-800 lg:w-2/3 lg:flex-none lg:border-b-0 lg:border-r">
			<div class="flex items-start justify-between gap-3">
				<div class="min-w-0">
					<div class="text-xs font-semibold text-gray-500 dark:text-gray-400">{{ receipt.name }}</div>
					<h2 class="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
						{{ receipt.title }}
					</h2>
				</div>
				<button
					type="button"
					class="rounded-md px-2 py-1 text-sm text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
					@click="emit('close')"
				>
					Close
				</button>
			</div>

			<dl class="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
				<div>
					<dt class="text-xs text-gray-500 dark:text-gray-400">Date</dt>
					<dd class="font-medium text-gray-900 dark:text-gray-100">{{ receipt.posting_date || "—" }}</dd>
				</div>
				<div>
					<dt class="text-xs text-gray-500 dark:text-gray-400">Sum</dt>
					<dd class="font-medium tabular-nums text-gray-900 dark:text-gray-100">{{ formatSum(receipt) }}</dd>
				</div>
				<div>
					<dt class="text-xs text-gray-500 dark:text-gray-400">Reference</dt>
					<dd class="font-medium text-gray-900 dark:text-gray-100">
						{{ receipt.supplier_reference || "—" }}
					</dd>
				</div>
				<div>
					<dt class="text-xs text-gray-500 dark:text-gray-400">Status</dt>
					<dd class="font-medium text-gray-900 dark:text-gray-100">{{ receipt.status }}</dd>
				</div>
				<div class="sm:col-span-2">
					<dt class="text-xs text-gray-500 dark:text-gray-400">Supplier</dt>
					<dd class="font-medium text-gray-900 dark:text-gray-100">
						{{ receipt.supplier_name || receipt.supplier || "—" }}
					</dd>
				</div>
			</dl>

			<div class="flex flex-wrap gap-2">
				<span
					v-if="receipt.sent_to_datev"
					class="rounded bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700 dark:bg-blue-950 dark:text-blue-300"
				>
					Sent to DATEV
				</span>
				<span
					v-if="receipt.is_paid"
					class="rounded bg-green-50 px-2 py-1 text-xs font-medium text-green-700 dark:bg-green-950 dark:text-green-300"
				>
					Is Paid
				</span>
			</div>

			<div v-if="receipt.has_pdf" class="rounded-md border border-gray-200 px-3 py-2 text-sm dark:border-gray-700">
				<span
					v-if="extractStatus === 'running'"
					class="text-gray-600 dark:text-gray-300"
				>
					Extracting data from PDF…
				</span>
				<span
					v-else-if="extractStatus === 'done'"
					class="text-green-700 dark:text-green-400"
				>
					Fields updated from PDF
					<span v-if="extractUpdatedCount"> ({{ extractUpdatedCount }} fields)</span>
				</span>
				<span
					v-else-if="extractStatus === 'failed'"
					class="text-red-600 dark:text-red-400"
				>
					{{ extractErrorMessage }}
				</span>
				<span v-else class="text-gray-500 dark:text-gray-400">
					PDF attached — extraction will start automatically.
				</span>
			</div>

			<div class="flex flex-col gap-2 sm:flex-row">
				<button
					type="button"
					class="inline-flex items-center justify-center rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-800 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800"
					:disabled="!receipt.has_pdf || extractStatus === 'running'"
					@click="emit('review-correct')"
				>
					Review &amp; correct
				</button>
				<a
					:href="receipt.desk_url"
					class="inline-flex items-center justify-center rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-800 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800"
				>
					Open in Desk
				</a>
			</div>
		</div>

		<div class="flex min-h-0 min-w-0 flex-col p-5 lg:w-1/3 lg:flex-none">
			<p class="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
				PDF Preview
			</p>
			<div
				v-if="!pdfUrl"
				class="flex flex-1 items-center justify-center rounded-md border border-dashed border-gray-300 bg-gray-50 px-4 text-center text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900/50 dark:text-gray-400"
			>
				No PDF attached — attach one in Desk or via email inbox.
			</div>
			<iframe
				v-else
				:src="pdfUrl"
				type="application/pdf"
				class="min-h-[360px] flex-1 rounded-md border border-gray-200 bg-gray-100 dark:border-gray-700 dark:bg-gray-800"
			/>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	receipt: { type: Object, required: true },
	extractStatus: { type: String, default: "idle" },
	extractUpdatedCount: { type: Number, default: 0 },
	extractErrorMessage: { type: String, default: "" },
})

const emit = defineEmits(["close", "review-correct"])

const pdfUrl = computed(() => {
	const url = (props.receipt?.attachment || "").trim()
	if (!url || !url.toLowerCase().endsWith(".pdf")) return ""
	return url.startsWith("http") ? url : `${window.location.origin}${url}`
})

function formatSum(receipt) {
	const amount = receipt.sum
	if (amount == null || amount === "") return "—"
	const n = Number(amount)
	const formatted = Number.isFinite(n)
		? n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
		: String(amount)
	return receipt.currency ? `${formatted} ${receipt.currency}` : formatted
}
</script>
