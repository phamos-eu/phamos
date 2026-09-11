<template>
	<div class="contents">
		<button
			v-for="row in rows"
			:key="row.name"
			type="button"
			class="border-b border-outline-gray-1 text-left hover:bg-surface-gray-2"
			:class="[
				MIS_LIST_FILTER_SUBGRID,
				'py-3',
				{
					'bg-surface-gray-2 shadow-[inset_3px_0_0_0_var(--outline-gray-4)]':
						row.name === selectedName,
				},
			]"
			@click="emit('select', row.name)"
		>
			<div class="min-w-0">
				<div class="truncate text-sm font-semibold text-ink-gray-9" :title="row.name">
					{{ row.name }}
				</div>
			</div>
			<div class="min-w-0 truncate text-sm text-ink-gray-8" :title="row.implementation || ''">
				{{ row.implementation || "—" }}
			</div>
			<div class="min-w-0 truncate text-sm text-ink-gray-8" :title="formatMisPeriod(row)">
				{{ formatMisPeriod(row) }}
			</div>
			<div class="flex min-w-0 justify-center">
				<Badge
					class="whitespace-nowrap"
					:label="row.status"
					:theme="statusTheme(row.status)"
					size="sm"
					variant="subtle"
				/>
			</div>
			<div class="min-w-0 text-center text-sm tabular-nums text-ink-gray-8">
				{{ formatHours(row.total_hours) }}
			</div>
			<div class="min-w-0 text-center text-sm tabular-nums text-ink-gray-8">
				{{ formatHours(row.billable_hours) }}
			</div>
			<div class="min-w-0 text-center text-sm tabular-nums">
				<span
					class="inline-flex flex-col items-center leading-tight"
					:class="deltaClass(row.delta_ratio)"
					:title="deltaTitle(row)"
				>
					<span class="font-medium">{{ formatHours(row.delta_hours) }}</span>
					<span class="text-xs opacity-90">{{ formatDeltaPercent(row.delta_ratio) }}</span>
				</span>
			</div>
			<div class="flex min-w-0 items-center justify-center pr-3">
				<AvatarGroup
					:users="assigneeUsersFromRow(row)"
					:limit="3"
					align="center"
				/>
			</div>
		</button>
	</div>
</template>

<script setup>
import { Badge } from "frappe-ui"
import AvatarGroup from "@spa/components/AvatarGroup.vue"
import { assigneeUsersFromRow } from "@spa/utils/avatar.js"
import {
	MIS_LIST_FILTER_SUBGRID,
	formatDeltaPercent,
	formatHours,
	formatMisPeriod,
	misDeltaTone,
	misStatusTheme,
} from "../misListColumns.js"

defineProps({
	rows: { type: Array, default: () => [] },
	selectedName: { type: String, default: null },
})

const emit = defineEmits(["select"])

function statusTheme(status) {
	return misStatusTheme(status)
}

function deltaClass(ratio) {
	const tone = misDeltaTone(ratio)
	const map = {
		green: "text-green-700 dark:text-green-400",
		amber: "text-amber-700 dark:text-amber-400",
		red: "text-red-700 dark:text-red-400",
		gray: "text-ink-gray-6",
	}
	return map[tone]
}

function deltaTitle(row) {
	const hours = formatHours(row.delta_hours)
	const pct = formatDeltaPercent(row.delta_ratio)
	return `Non-billable: ${hours} h (${pct} of total)`
}
</script>
