<template>
	<!-- Grid-aligned rows, columns kept in sync with the LeadsFollowUps toolbar via LEAD_LIST_FILTER_SUBGRID. -->
	<div class="contents">
		<button
			v-for="lead in leads"
			:key="lead.name"
			type="button"
			:class="[LEAD_LIST_FILTER_SUBGRID, 'border-b border-outline-gray-1 py-3 text-left hover:bg-surface-gray-2']"
			@click="emit('select', lead.name)"
		>
			<div class="min-w-0">
				<div class="truncate text-sm font-medium text-ink-gray-9" :title="lead.lead_name || lead.name">
					{{ lead.lead_name || lead.name }}
				</div>
				<div v-if="lead.company_name" class="truncate text-xs text-ink-gray-6">{{ lead.company_name }}</div>
				<div v-if="lead.owner_name" class="mt-0.5 truncate text-xs text-ink-gray-5">{{ lead.owner_name }}</div>
			</div>
			<div class="flex min-w-0 flex-wrap items-center justify-center gap-1.5">
				<Badge class="whitespace-nowrap" :label="lead.status" :theme="leadStatusTheme(lead.status)" size="sm" variant="subtle" />
			</div>
			<div class="min-w-0 text-center text-xs text-ink-gray-6">
				<Badge
					v-if="lead.overdue"
					class="whitespace-nowrap"
					label="Overdue"
					theme="red"
					size="sm"
					variant="subtle"
				/>
				<Badge
					v-else-if="!lead.custom_next_followup"
					class="whitespace-nowrap"
					label="No date"
					theme="orange"
					size="sm"
					variant="subtle"
				/>
				<span v-else>{{ formatDatetime(lead.custom_next_followup) }}</span>
			</div>
			<div class="min-w-0 text-center text-xs text-ink-gray-6">
				{{ lead.modified ? formatDate(lead.modified) : "—" }}
			</div>
		</button>
		<div
			v-if="!leads.length"
			style="grid-column: 1 / -1"
			class="flex flex-col items-center justify-center gap-1 px-6 py-16 text-center text-sm text-ink-gray-6"
		>
			No leads found
		</div>
	</div>
</template>

<script setup>
import { Badge } from "frappe-ui"
import { formatDate, formatDatetime } from "@spa/utils/datetime"
import { LEAD_LIST_FILTER_SUBGRID, leadStatusTheme } from "@/leadListColumns.js"

defineProps({
	leads: { type: Array, default: () => [] },
})

const emit = defineEmits(["select"])
</script>
