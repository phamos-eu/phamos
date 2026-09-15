<template>
	<div class="min-h-0 flex-1 overflow-y-auto">
		<button
			v-for="lead in leads"
			:key="lead.name"
			type="button"
			class="block w-full border-b border-outline-gray-1 px-4 py-3 text-left hover:bg-surface-gray-2"
			:class="{
				'bg-surface-gray-2 shadow-[inset_3px_0_0_0_var(--outline-gray-4)]': lead.name === selectedName,
			}"
			@click="emit('select', lead.name)"
		>
			<div class="mb-1 flex flex-wrap items-center gap-1.5">
				<Badge class="whitespace-nowrap" :label="lead.status" :theme="statusTheme(lead.status)" size="sm" variant="subtle" />
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
			</div>
			<div class="truncate text-sm font-medium text-ink-gray-9" :title="lead.lead_name || lead.name">
				{{ lead.lead_name || lead.name }}
			</div>
			<div v-if="lead.company_name" class="truncate text-xs text-ink-gray-6">{{ lead.company_name }}</div>
			<div class="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-ink-gray-6">
				<span v-if="lead.custom_next_followup">Next: {{ formatDatetime(lead.custom_next_followup) }}</span>
				<span v-if="!compact && lead.owner_name">Owner: {{ lead.owner_name }}</span>
				<span v-if="!compact && (lead.mobile_no || lead.phone)">{{ lead.mobile_no || lead.phone }}</span>
			</div>
		</button>
		<div v-if="!leads.length" class="flex flex-1 flex-col items-center justify-center gap-1 px-6 py-16 text-center text-sm text-ink-gray-6">
			No leads found
		</div>
	</div>
</template>

<script setup>
import { Badge } from "frappe-ui"
import { formatDatetime } from "@spa/utils/datetime"

defineProps({
	leads: { type: Array, default: () => [] },
	selectedName: { type: String, default: null },
	compact: { type: Boolean, default: false },
})

const emit = defineEmits(["select"])

function statusTheme(status) {
	const map = {
		Lead: "gray",
		Open: "blue",
		Replied: "blue",
		Opportunity: "orange",
		Quotation: "orange",
		"Lost Quotation": "gray",
		Interested: "green",
		Converted: "green",
		"Do Not Contact": "red",
	}
	return map[status] || "gray"
}
</script>
