<template>
	<div class="overflow-x-auto rounded-md border border-outline-gray-2">
		<table class="w-full text-sm">
			<thead class="bg-surface-gray-1 text-xs text-ink-gray-5">
				<tr>
					<th class="px-3 py-2 text-left font-medium">Period</th>
					<th class="px-3 py-2 text-left font-medium">Type</th>
					<th class="px-3 py-2 text-right font-medium">FTE</th>
					<th class="px-3 py-2 text-right font-medium">Weekly</th>
					<th class="px-3 py-2 text-right font-medium">Monthly gross</th>
					<th class="px-3 py-2 text-left font-medium">Status</th>
				</tr>
			</thead>
			<tbody>
				<tr
					v-for="row in rows"
					:key="row.name"
					:tabindex="clickable ? 0 : undefined"
					class="border-t border-outline-gray-1"
					:class="[
						{ 'bg-surface-gray-2 font-semibold': row.name === currentName },
						clickable && 'cursor-pointer hover:bg-surface-gray-2 focus:bg-surface-gray-2 focus:outline-none',
					]"
					@click="clickable && emit('open', row.name)"
					@keydown.enter="clickable && emit('open', row.name)"
				>
					<td class="px-3 py-2 text-ink-gray-9">{{ formatPeriod(row) }}</td>
					<td class="px-3 py-2 text-ink-gray-8">{{ row.contract_type }}</td>
					<td class="px-3 py-2 text-right tabular-nums">{{ formatPercent(row.fte_percentage) }}</td>
					<td class="px-3 py-2 text-right tabular-nums">{{ formatHours(row.weekly_hours) }}</td>
					<td class="px-3 py-2 text-right tabular-nums">{{ formatMoney(row.monthly_gross, row.currency) }}</td>
					<td class="px-3 py-2"><ContractStatusBadge :status="row.status" /></td>
				</tr>
			</tbody>
		</table>
	</div>
</template>

<script setup>
import ContractStatusBadge from "./ContractStatusBadge.vue"
import { formatHours, formatMoney, formatPercent, formatPeriod } from "./contractFormat.js"

defineProps({
	rows: { type: Array, default: () => [] },
	currentName: { type: String, default: "" },
	/** Rows open a contract on click/Enter (HR cockpit); read-only otherwise (Personal cockpit). */
	clickable: { type: Boolean, default: false },
})

const emit = defineEmits(["open"])
</script>
