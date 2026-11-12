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
				<!-- Why a lead sits where it does — most often the "Do Not Contact"
				     reason — without having to open it. -->
				<div
					v-if="lead.custom_status_comment"
					class="truncate text-xs italic text-ink-gray-5"
					:title="lead.custom_status_comment"
				>
					{{ lead.custom_status_comment }}
				</div>
			</div>
			<div class="flex min-w-0 flex-wrap items-center justify-center gap-1.5">
				<Badge class="whitespace-nowrap" :label="leadStatusLabel(lead.status)" :theme="leadStatusTheme(lead.status)" size="sm" variant="subtle" />
			</div>
			<div class="min-w-0 text-center text-xs text-ink-gray-6">
				<Badge
					v-if="lead.overdue"
					class="whitespace-nowrap"
					:label="__('Overdue')"
					theme="red"
					size="sm"
					variant="subtle"
				/>
				<Badge
					v-else-if="!lead.custom_next_followup"
					class="whitespace-nowrap"
					:label="__('No date')"
					theme="orange"
					size="sm"
					variant="subtle"
				/>
				<span v-else>{{ formatDate(lead.custom_next_followup) }}</span>
			</div>
			<div class="min-w-0 text-center text-xs text-ink-gray-6">
				<template v-if="showCreated">{{ lead.creation ? formatDate(String(lead.creation).slice(0, 10)) : "—" }}</template>
				<template v-else>{{ lead.modified ? formatDate(String(lead.modified).slice(0, 10)) : "—" }}</template>
			</div>
			<div class="flex min-w-0 items-center justify-center pr-3">
				<UserAvatar
					v-if="lead.lead_owner"
					:name="lead.lead_owner"
					:label="lead.owner_name || lead.lead_owner"
					:image="lead.owner_image"
					size="sm"
				/>
				<span v-else class="text-xs text-ink-gray-5">—</span>
			</div>
		</button>
		<div
			v-if="!leads.length"
			style="grid-column: 1 / -1"
			class="flex flex-col items-center justify-center gap-1 px-6 py-16 text-center text-sm text-ink-gray-6"
		>
			{{ __("No leads found") }}
		</div>
	</div>
</template>

<script setup>
import { Badge } from "frappe-ui"
import UserAvatar from "@spa/components/UserAvatar.vue"
import { formatDate } from "@spa/utils/datetime"
import { LEAD_LIST_FILTER_SUBGRID, leadStatusLabel, leadStatusTheme } from "@/leadListColumns.js"

defineProps({
	leads: { type: Array, default: () => [] },
	// Lists from the lead overview are about when a lead came in, not when it was last touched.
	showCreated: { type: Boolean, default: false },
})

const emit = defineEmits(["select"])
</script>
