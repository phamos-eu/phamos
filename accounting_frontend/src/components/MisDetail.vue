<template>
	<div class="flex h-full min-h-0 w-full flex-1 flex-col overflow-hidden">
		<div class="flex items-start justify-between gap-3 border-b border-outline-gray-2 px-5 py-4">
			<div class="min-w-0">
				<div class="text-xs font-semibold text-ink-gray-6">{{ summary.name }}</div>
				<h2 class="mt-1 truncate text-lg font-semibold text-ink-gray-9">
					{{ summary.implementation || "—" }}
				</h2>
				<p v-if="periodLabel" class="mt-1 text-sm text-ink-gray-6">{{ periodLabel }}</p>
			</div>
			<button
				type="button"
				class="rounded-md px-2 py-1 text-sm text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				@click="emit('close')"
			>
				Close
			</button>
		</div>

		<div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
			<dl class="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
				<div>
					<dt class="text-xs text-ink-gray-5">Status</dt>
					<dd class="mt-1">
						<Badge
							:label="summary.status"
							:theme="statusTheme(summary.status)"
							size="sm"
							variant="subtle"
						/>
					</dd>
				</div>
				<div>
					<dt class="text-xs text-ink-gray-5">Period</dt>
					<dd class="mt-1 font-medium text-ink-gray-9">{{ periodLabel || "—" }}</dd>
				</div>
				<div>
					<dt class="text-xs text-ink-gray-5">Total Hours</dt>
					<dd class="mt-1 font-medium tabular-nums text-ink-gray-9">
						{{ formatHours(summary.total_hours) }}
					</dd>
				</div>
				<div>
					<dt class="text-xs text-ink-gray-5">Billable Hours</dt>
					<dd class="mt-1 font-medium tabular-nums text-ink-gray-9">
						{{ formatHours(summary.billable_hours) }}
					</dd>
				</div>
				<div class="sm:col-span-2">
					<dt class="text-xs text-ink-gray-5">Non-billable Delta</dt>
					<dd class="mt-1 font-medium tabular-nums" :class="deltaClass">
						{{ formatHours(summary.delta_hours) }}
						<span class="text-sm font-normal opacity-90">
							({{ formatDeltaPercent(summary.delta_ratio) }} of total)
						</span>
					</dd>
				</div>
			</dl>
		</div>
	</div>

	<Teleport v-if="propertiesHostReady" to="#mis-properties-host">
		<div class="flex h-full min-h-0 flex-col bg-surface-white text-ink-gray-9">
			<div class="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-4">
				<section>
					<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
						Status
					</div>
					<Badge
						:label="summary.status"
						:theme="statusTheme(summary.status)"
						size="sm"
						variant="subtle"
					/>
				</section>

				<section>
					<AssigneePicker
						v-model="assignees"
						:assignee-details="assigneeDetails"
						:shortlist-users="options.shortlist_users || []"
						:api-prefix="API"
						:document-name="summary.name"
						method-name="set_monthly_implementation_summary_assignees"
						@updated="onAssigneesUpdated"
					/>
				</section>
			</div>

			<div class="mt-auto flex-shrink-0 space-y-2 border-t border-outline-gray-2 p-4">
				<a
					:href="summary.desk_url"
					class="flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm font-medium text-ink-gray-7 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				>
					<FeatherIcon name="external-link" class="h-4 w-4 flex-shrink-0" />
					<span class="truncate">Open in Desk</span>
				</a>
			</div>
		</div>
	</Teleport>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue"
import { Badge } from "frappe-ui"
import AssigneePicker from "@spa/components/AssigneePicker.vue"
import {
	formatDeltaPercent,
	formatHours,
	misDeltaTone,
	misStatusTheme,
} from "../misListColumns.js"
import spaConfig from "@/config"

const props = defineProps({
	summary: { type: Object, required: true },
	options: {
		type: Object,
		default: () => ({
			shortlist_users: [],
		}),
	},
	apiPrefix: {
		type: String,
		default: "",
	},
})

const emit = defineEmits(["close", "updated"])

const API = computed(() => props.apiPrefix || spaConfig.api)
const propertiesHostReady = ref(false)
const assignees = ref([...(props.summary.assignees || [])])

const periodLabel = computed(() => {
	const parts = [props.summary.month, props.summary.year].filter(Boolean)
	return parts.join(" ")
})

const assigneeDetails = computed(() => {
	const names = props.summary.assignees || []
	const labels = props.summary.assignee_names || []
	const images = props.summary.assignee_images || []
	return names.map((name, i) => ({
		name,
		full_name: labels[i] || name,
		user_image: images[i] || "",
	}))
})

const deltaClass = computed(() => {
	const tone = misDeltaTone(props.summary.delta_ratio)
	const map = {
		green: "text-green-700 dark:text-green-400",
		amber: "text-amber-700 dark:text-amber-400",
		red: "text-red-700 dark:text-red-400",
		gray: "text-ink-gray-6",
	}
	return map[tone]
})

function statusTheme(status) {
	return misStatusTheme(status)
}

function onAssigneesUpdated(updated) {
	if (updated?.assignees) {
		assignees.value = [...updated.assignees]
	}
	emit("updated", updated)
}

watch(
	() => props.summary,
	(summary) => {
		assignees.value = [...(summary.assignees || [])]
	}
)

onMounted(async () => {
	await nextTick()
	propertiesHostReady.value = Boolean(document.getElementById("mis-properties-host"))
})
</script>
