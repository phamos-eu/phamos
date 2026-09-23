<template>
	<div class="flex h-full min-h-0 flex-col overflow-y-auto p-5">
		<header class="mb-4 flex items-start justify-between gap-3">
			<div class="min-w-0">
				<div class="text-xs font-semibold text-gray-500 dark:text-gray-400">Checklist</div>
				<h2 class="mt-1 truncate text-lg font-semibold leading-snug text-gray-900 dark:text-gray-100">
					{{ checklist.name }}
				</h2>
			</div>
			<div class="flex flex-shrink-0 items-center gap-2">
				<Button variant="ghost" :link="checklist.desk_url">Open in Desk</Button>
				<Button variant="ghost" @click="emit('close')">Close</Button>
			</div>
		</header>

		<section class="mb-5 grid grid-cols-2 gap-3 text-sm">
			<div>
				<div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
					Status
				</div>
				<div>{{ checklist.status || "—" }}</div>
			</div>
			<div>
				<div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
					Progress
				</div>
				<div>
					{{ checklist.done_count || 0 }}/{{ checklist.total_count || 0 }}
					<span class="text-gray-500 dark:text-gray-400">
						({{ Math.round(checklist.completion_percentage || 0) }}%)
					</span>
				</div>
			</div>
			<div v-if="checklist.document">
				<div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
					Linked
				</div>
				<a
					v-if="checklist.reference_record"
					:href="deskRecordUrl(checklist.document, checklist.reference_record)"
					target="_blank"
					rel="noopener noreferrer"
					class="inline-flex max-w-full items-center gap-1 font-medium text-ink-gray-8 underline-offset-2 hover:underline"
				>
					<span class="truncate">
						{{ checklist.document }} / {{ checklist.reference_record }}
					</span>
					<FeatherIcon name="external-link" class="h-3.5 w-3.5 flex-shrink-0" />
				</a>
				<div v-else>{{ checklist.document }}</div>
			</div>
		</section>

		<section class="mb-5 min-h-0 flex-1">
			<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
				Items
			</div>
			<ChecklistEditor :checklist="checklist" @updated="emit('updated', $event)" />
		</section>
	</div>
</template>

<script setup>
import ChecklistEditor from "@spa/components/ChecklistEditor.vue"
import { deskRecordUrl } from "@spa/utils/deskUrl.js"

defineProps({
	checklist: { type: Object, required: true },
})

const emit = defineEmits(["close", "updated"])
</script>
