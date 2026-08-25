<template>
	<div class="min-h-0 flex-1 overflow-x-auto overflow-y-hidden">
		<div class="flex h-full min-h-[280px] gap-3 p-3">
			<div
				v-for="col in columns"
				:key="col"
				class="flex w-60 flex-none flex-col rounded-lg bg-gray-50 dark:bg-gray-800/60"
				@dragover.prevent
				@drop="onDrop(col, $event)"
			>
				<div
					class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2 dark:border-gray-700"
				>
					<span class="text-xs font-semibold uppercase tracking-wide text-gray-600 dark:text-gray-400">
						{{ col }}
					</span>
					<span class="rounded-full bg-white px-1.5 py-0.5 text-[11px] text-gray-500 dark:bg-gray-900 dark:text-gray-400">
						{{ byStatus[col]?.length || 0 }}
					</span>
				</div>
				<div class="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
					<div
						v-for="receipt in byStatus[col] || []"
						:key="receipt.name"
						draggable="true"
						class="cursor-pointer rounded-md border border-gray-200 bg-white px-2.5 py-2 shadow-sm hover:border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:hover:border-gray-600"
						:class="{
							'ring-2 ring-gray-900 ring-offset-1 dark:ring-gray-100 dark:ring-offset-gray-900':
								receipt.name === selectedName,
						}"
						@dragstart="onDragStart(receipt, $event)"
						@click="emit('select', receipt.name)"
					>
						<div class="mb-1 flex items-center justify-between gap-2">
							<span class="text-[11px] font-semibold text-gray-500 dark:text-gray-400">{{ receipt.name }}</span>
							<span v-if="receipt.posting_date" class="text-[11px] text-gray-500 dark:text-gray-400">
								{{ formatDate(receipt.posting_date) }}
							</span>
						</div>
						<div class="mb-1 text-sm font-medium leading-snug text-gray-900 dark:text-gray-100">
							{{ receipt.title }}
						</div>
						<div class="mb-1 text-sm font-semibold tabular-nums text-gray-800 dark:text-gray-200">
							{{ formatSum(receipt) }}
						</div>
						<div
							v-if="receipt.supplier_reference"
							class="truncate text-[11px] text-gray-500 dark:text-gray-400"
							:title="receipt.supplier_reference"
						>
							Ref: {{ receipt.supplier_reference }}
						</div>
						<div class="mt-1.5 flex flex-wrap gap-1">
							<span
								v-if="receipt.sent_to_datev"
								class="rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-700 dark:bg-blue-950 dark:text-blue-300"
							>
								DATEV
							</span>
							<span
								v-if="receipt.is_paid"
								class="rounded bg-green-50 px-1.5 py-0.5 text-[10px] font-medium text-green-700 dark:bg-green-950 dark:text-green-300"
							>
								Paid
							</span>
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { formatDate } from "@spa/utils/datetime"

const COLUMNS = [
	"Inbox",
	"Needs Decision",
	"Approved to Pay",
	"Do Not Pay",
	"Sent to DATEV",
	"Paid",
]

const props = defineProps({
	receipts: { type: Array, default: () => [] },
	selectedName: { type: String, default: null },
})

const emit = defineEmits(["select", "status-change"])

const columns = COLUMNS

const byStatus = computed(() => {
	const map = Object.fromEntries(COLUMNS.map((c) => [c, []]))
	for (const receipt of props.receipts) {
		const status = COLUMNS.includes(receipt.status) ? receipt.status : "Inbox"
		map[status].push(receipt)
	}
	return map
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

function onDragStart(receipt, event) {
	event.dataTransfer.setData("text/plain", receipt.name)
	event.dataTransfer.effectAllowed = "move"
}

function onDrop(col, event) {
	const name = event.dataTransfer.getData("text/plain")
	if (!name) return
	const receipt = props.receipts.find((r) => r.name === name)
	if (!receipt || receipt.status === col) return
	emit("status-change", { name, status: col })
}
</script>
