<template>
	<div class="flex h-full min-h-0 flex-col overflow-y-auto p-5">
		<header class="mb-4 flex items-start justify-between gap-3">
			<div class="min-w-0">
				<div class="text-xs font-semibold text-gray-500">Checklist</div>
				<h2 class="mt-1 truncate text-lg font-semibold leading-snug text-gray-900">
					{{ checklist.name }}
				</h2>
			</div>
			<button
				class="rounded-md px-2 py-1 text-xl leading-none text-gray-500 hover:bg-gray-100"
				title="Close"
				@click="emit('close')"
			>
				×
			</button>
		</header>

		<section class="mb-5 grid grid-cols-2 gap-3 text-sm">
			<div>
				<div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500">
					Status
				</div>
				<div>{{ checklist.status || "—" }}</div>
			</div>
			<div>
				<div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500">
					Progress
				</div>
				<div>
					{{ checklist.done_count || 0 }}/{{ checklist.total_count || 0 }}
					<span class="text-gray-500">
						({{ Math.round(checklist.completion_percentage || 0) }}%)
					</span>
				</div>
			</div>
			<div v-if="checklist.document">
				<div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500">
					Linked
				</div>
				<div>
					{{ checklist.document }}
					<span v-if="checklist.reference_record"> / {{ checklist.reference_record }}</span>
				</div>
			</div>
		</section>

		<section class="mb-5 min-h-0 flex-1">
			<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500">
				Items
			</div>
			<ChecklistEditor :checklist="checklist" @updated="emit('updated', $event)" />
		</section>

		<footer class="mt-auto border-t border-gray-200 pt-4">
			<a
				:href="checklist.desk_url"
				class="inline-flex rounded-md border border-gray-200 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
			>
				Open in Desk
			</a>
		</footer>
	</div>
</template>

<script setup>
import ChecklistEditor from "./ChecklistEditor.vue"

defineProps({
	checklist: { type: Object, required: true },
})

const emit = defineEmits(["close", "updated"])
</script>
