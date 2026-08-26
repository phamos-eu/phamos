<template>
	<section class="mb-5">
		<div class="mb-2 flex items-center justify-between gap-2">
			<div class="text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
				Checklists
			</div>
			<Button size="sm" @click="showCreate = true">New checklist</Button>
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
				<button
					type="button"
					class="flex w-full items-center gap-2 px-3 py-2.5 text-left hover:bg-gray-50 dark:hover:bg-gray-800"
					@click="toggleExpand(row.name)"
				>
					<span class="text-xs text-gray-400">{{ expanded[row.name] ? "▼" : "▶" }}</span>
					<span class="min-w-0 flex-1 truncate text-sm font-medium text-gray-900 dark:text-gray-100">
						{{ row.name }}
					</span>
					<span
						class="rounded-full px-1.5 py-0.5 text-[10px] font-semibold"
						:class="statusClass(row.status)"
					>
						{{ row.status }}
					</span>
					<span class="text-[11px] tabular-nums text-gray-500">
						{{ row.done_count || 0 }}/{{ row.total_count || 0 }}
					</span>
				</button>

				<div v-if="expanded[row.name]" class="border-t border-gray-100 px-3 py-3 dark:border-gray-800">
					<div
						v-if="detailLoading[row.name] && !details[row.name]"
						class="text-sm text-gray-500 dark:text-gray-400"
					>
						Loading items…
					</div>
					<template v-else-if="details[row.name]">
						<ChecklistEditor
							:checklist="details[row.name]"
							compact
							@updated="(payload) => onChecklistUpdated(row.name, payload)"
						/>
						<button
							type="button"
							class="mt-3 text-xs text-blue-600 hover:underline dark:text-blue-400"
							@click="openInChecklists(row.name)"
						>
							Open in Checklists
						</button>
					</template>
				</div>
			</div>
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
import { useRouter } from "vue-router"
import { call } from "frappe-ui"
import ChecklistEditor from "@spa/components/ChecklistEditor.vue"
import CreateChecklistDialog from "@spa/components/CreateChecklistDialog.vue"

const props = defineProps({
	document: { type: String, required: true },
	referenceRecord: { type: String, required: true },
	referenceTitle: { type: String, default: "" },
})

const API = "phamos.api.checklist_inbox"
const router = useRouter()

const loading = ref(false)
const summaries = ref([])
const expanded = reactive({})
const details = reactive({})
const detailLoading = reactive({})
const showCreate = ref(false)

function statusClass(status) {
	if (status === "Completed") return "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300"
	if (status === "In Progress") return "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
	if (status === "Not Started") return "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"
	return "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300"
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

function onChecklistUpdated(name, payload) {
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
}

async function onChecklistCreated(created) {
	await loadSummaries()
	expanded[created.name] = true
	details[created.name] = created
}

function openInChecklists(name) {
	// Checklist inbox route exists on I Own My Work; other cockpits skip navigation.
	if (router.hasRoute("ChecklistDetail")) {
		router.push({ name: "ChecklistDetail", params: { name } })
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
