<template>
	<section class="mb-5">
		<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
			Checklists
		</div>

		<div v-if="loading" class="text-sm text-gray-500 dark:text-gray-400">Loading checklists…</div>
		<div v-else-if="!summaries.length" class="text-sm text-gray-500 dark:text-gray-400">
			No checklists linked yet.
		</div>
		<div v-else class="space-y-2">
			<div
				v-for="row in summaries"
				:key="row.name"
				class="rounded-md border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900"
			>
				<div
					class="flex w-full items-center gap-1 px-2 py-1.5 hover:bg-surface-gray-2 dark:hover:bg-gray-800"
				>
					<Button
						variant="ghost"
						theme="gray"
						size="sm"
						:icon="expanded[row.name] ? 'chevron-down' : 'chevron-right'"
						:label="expanded[row.name] ? 'Collapse checklist' : 'Expand checklist'"
						@click="toggleExpand(row.name)"
					/>
					<button
						type="button"
						class="flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-1 text-left"
						@click="toggleExpand(row.name)"
					>
						<span class="min-w-0 flex-1 truncate text-sm font-medium text-ink-gray-8 dark:text-gray-100">
							{{ row.title || row.name }}
						</span>
						<Badge
							:label="`${row.status} ${row.done_count || 0}/${row.total_count || 0}`"
							:theme="statusTheme(row.status)"
							size="sm"
							variant="subtle"
						/>
					</button>
				</div>

				<div v-if="expanded[row.name]" class="border-t border-gray-100 px-3 py-3 dark:border-gray-800">
					<div
						v-if="detailLoading[row.name] && !details[row.name]"
						class="text-sm text-gray-500 dark:text-gray-400"
					>
						Loading items…
					</div>
					<ChecklistEditor
						v-else-if="details[row.name]"
						:checklist="details[row.name]"
						compact
						@updated="(payload) => onChecklistUpdated(row.name, payload)"
					/>
				</div>
			</div>
		</div>

		<div class="mt-3">
			<Button size="sm" @click="showCreate = true">New checklist</Button>
		</div>

		<CreateChecklistDialog
			v-model="showCreate"
			:document="document"
			:reference-record="referenceRecord"
			:reference-title="referenceTitle"
			@created="onChecklistCreated"
		/>
	</section>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from "vue"
import { Badge, call } from "frappe-ui"
import ChecklistEditor from "@spa/components/ChecklistEditor.vue"
import CreateChecklistDialog from "@spa/components/CreateChecklistDialog.vue"

const props = defineProps({
	document: { type: String, required: true },
	referenceRecord: { type: String, required: true },
	referenceTitle: { type: String, default: "" },
})

const API = "phamos.api.checklist_inbox"

const loading = ref(false)
const summaries = ref([])
const expanded = reactive({})
const details = reactive({})
const detailLoading = reactive({})
const showCreate = ref(false)

function statusTheme(status) {
	if (status === "Completed") return "green"
	if (status === "In Progress") return "orange"
	return "gray"
}

function applyDefaultExpansion(rows) {
	Object.keys(expanded).forEach((k) => delete expanded[k])
	const toLoad = []
	for (const row of rows) {
		const open = row.status !== "Completed"
		expanded[row.name] = open
		if (open) toLoad.push(row.name)
	}
	return toLoad
}

async function loadSummaries() {
	if (!props.referenceRecord) {
		summaries.value = []
		return
	}
	loading.value = true
	try {
		summaries.value = await call(`${API}.get_checklists_for_reference`, {
			document: props.document,
			reference_record: props.referenceRecord,
		})
		const toLoad = applyDefaultExpansion(summaries.value)
		await Promise.all(toLoad.map((name) => loadDetail(name)))
	} finally {
		loading.value = false
	}
}

async function loadDetail(name) {
	detailLoading[name] = true
	try {
		details[name] = await call(`${API}.get_checklist`, { name })
	} finally {
		detailLoading[name] = false
	}
}

async function toggleExpand(name) {
	expanded[name] = !expanded[name]
	if (expanded[name] && !details[name]) {
		await loadDetail(name)
	}
}

async function onChecklistUpdated(name, payload) {
	const previousStatus = summaries.value.find((r) => r.name === name)?.status
	details[name] = payload
	const idx = summaries.value.findIndex((r) => r.name === name)
	if (idx >= 0) {
		summaries.value[idx] = {
			...summaries.value[idx],
			status: payload.status,
			completion_percentage: payload.completion_percentage,
			done_count: payload.done_count,
			total_count: payload.total_count,
		}
	}
	if (payload.status === "Completed") {
		expanded[name] = false
	} else if (previousStatus === "Completed" && payload.status !== "Completed") {
		expanded[name] = true
		if (!details[name]) await loadDetail(name)
	}
}

async function onChecklistCreated(created) {
	await loadSummaries()
	if (created?.name) {
		expanded[created.name] = created.status !== "Completed"
		details[created.name] = created
	}
}

watch(
	() => props.referenceRecord,
	() => {
		Object.keys(expanded).forEach((k) => delete expanded[k])
		Object.keys(details).forEach((k) => delete details[k])
		loadSummaries()
	}
)

onMounted(loadSummaries)
</script>
