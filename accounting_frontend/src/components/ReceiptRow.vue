<template>
	<button
		type="button"
		class="grid w-full grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_7rem_7rem_minmax(0,1.4fr)] items-center gap-3 border-b border-outline-gray-1 px-5 py-2 text-left text-sm hover:bg-surface-gray-1"
		:class="active ? 'bg-surface-gray-2' : ''"
		@click="emit('open', item.name)"
	>
		<div class="min-w-0">
			<div class="truncate font-medium text-ink-gray-9">{{ item.supplier_name || item.supplier || item.title }}</div>
			<div class="truncate text-xs text-ink-gray-5">
				{{ item.name }}<span v-if="item.supplier_reference"> · {{ item.supplier_reference }}</span>
				<span v-if="item.receipt_type"> · {{ item.receipt_type }}</span>
			</div>
		</div>
		<div class="truncate text-xs text-ink-gray-6" :title="item.title">{{ item.title }}</div>
		<div class="text-right tabular-nums text-ink-gray-9">{{ money(item.sum, item.currency) }}</div>
		<div class="text-xs" :class="item.overdue_days ? 'font-medium text-ink-red-4' : 'text-ink-gray-6'">
			<template v-if="item.overdue_days">{{ item.overdue_days }} d overdue</template>
			<template v-else-if="item.due_date">due {{ formatDate(item.due_date) }}</template>
			<template v-else-if="item.posting_date">{{ formatDate(item.posting_date) }}</template>
		</div>
		<div class="flex min-w-0 items-center gap-2">
			<span v-if="item.ai_confidence" class="flex-none rounded px-1.5 py-0.5 text-[11px] font-medium" :class="confidenceClass(item.ai_confidence)">
				{{ Math.round(item.ai_confidence) }} %
			</span>
			<span class="truncate text-xs" :class="item.reason ? 'text-ink-amber-3' : 'text-ink-gray-5'" :title="(item.reasons || []).join(' · ')">
				{{ item.reason || statusText(item) }}
			</span>
		</div>
	</button>
</template>

<script setup>
import { formatDate } from "@spa/utils/datetime"

defineProps({
	item: { type: Object, required: true },
	active: { type: Boolean, default: false },
})
const emit = defineEmits(["open"])

function money(value, currency) {
	if (value == null || value === "") return "—"
	const n = Number(value)
	const text = Number.isFinite(n) ? n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : String(value)
	return currency ? `${text} ${currency}` : text
}

function confidenceClass(value) {
	if (value >= 90) return "bg-surface-green-2 text-ink-green-3"
	if (value >= 60) return "bg-surface-amber-2 text-ink-amber-3"
	return "bg-surface-red-2 text-ink-red-4"
}

function statusText(item) {
	const parts = [item.status]
	if (item.sent_to_datev) parts.push("sent to DATEV")
	if (item.is_paid) parts.push("paid")
	return parts.join(" · ")
}
</script>
