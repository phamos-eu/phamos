<template>
	<!-- Another department's Task in the company view (#1948): read-only, changes happen in its cockpit. -->
	<div class="flex h-full min-h-0 flex-col bg-surface-white text-ink-gray-9 dark:bg-surface-gray-1">
		<div class="flex items-start gap-2 border-b border-outline-gray-2 p-4">
			<div class="min-w-0 flex-1">
				<div class="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
					<span class="h-2.5 w-2.5 flex-shrink-0 rounded-full" :style="{ backgroundColor: task.cockpit.color }" />
					{{ task.cockpit.label }}
				</div>
				<div class="text-base font-bold leading-snug">{{ task.subject }}</div>
				<div class="mt-0.5 text-xs text-ink-gray-5">{{ task.name }}</div>
			</div>
			<button
				type="button"
				class="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				:aria-label="__('Close')"
				@click="emit('close')"
			>
				<FeatherIcon name="x" class="h-4 w-4" />
			</button>
		</div>

		<div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4 text-sm">
			<Button variant="solid" class="w-full" @click="openInCockpit">
				<template #prefix><FeatherIcon name="external-link" class="h-4 w-4" /></template>
				{{ __("Open in {0} Cockpit", [task.cockpit.label]) }}
			</Button>

			<dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
				<dt class="text-ink-gray-5">{{ __("Status") }}</dt>
				<dd>{{ task.status }}</dd>
				<dt class="text-ink-gray-5">{{ __("Priority") }}</dt>
				<dd>{{ task.priority || "–" }}</dd>
				<dt class="text-ink-gray-5">{{ __("Dates") }}</dt>
				<dd>{{ dateRange }}</dd>
				<dt class="text-ink-gray-5">{{ __("Progress") }}</dt>
				<dd class="flex items-center gap-2">
					<div class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-gray-3">
						<div
							class="h-full rounded-full"
							:style="{ width: `${progress}%`, backgroundColor: task.cockpit.color }"
						/>
					</div>
					<span class="text-xs text-ink-gray-6">{{ progress }} %</span>
				</dd>
				<dt class="text-ink-gray-5">{{ __("Task Owner") }}</dt>
				<dd>{{ task.custom_task_owner_name || "–" }}</dd>
				<dt class="text-ink-gray-5">{{ __("Assigned To") }}</dt>
				<dd>{{ (task.assignee_names || []).join(", ") || "–" }}</dd>
			</dl>

			<section v-if="task.description">
				<div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
					{{ __("Description") }}
				</div>
				<!-- TextEditor renders through its schema, so the stored HTML is not injected as is. -->
				<TextEditor :content="task.description" :editable="false" editor-class="prose-sm max-w-none" />
			</section>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { Button, FeatherIcon, TextEditor } from "frappe-ui"
import { formatDate } from "@spa/utils/datetime"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	// get_company_task of the General Management Cockpit: task detail plus `cockpit`.
	task: { type: Object, required: true },
})

const emit = defineEmits(["close"])

const progress = computed(() => Math.round(Math.min(100, Math.max(0, Number(props.task.progress) || 0))))

const dateRange = computed(() => {
	const start = props.task.exp_start_date
	const end = props.task.exp_end_date
	if (!start && !end) return "–"
	return [start, end].filter(Boolean).map(formatDate).join(" – ")
})

function openInCockpit() {
	const url = `${props.task.cockpit.route}/tasks/gantt/${encodeURIComponent(props.task.name)}`
	window.open(url, "_blank", "noopener")
}
</script>
