<template>
	<div class="flex h-full min-h-0">
		<section
			class="flex min-w-0 flex-col border-r border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
			:class="selectedName ? 'w-1/3 flex-none' : 'flex-1'"
		>
			<div
				class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-5 py-3 dark:border-gray-800"
			>
				<div class="flex flex-wrap items-center gap-3">
					<FormControl v-model="search" type="text" size="sm" placeholder="Search…" class="w-44" />
					<InboxStatusFilter
						v-model="includeCompleted"
						active-label="Active checklists"
						include-label="Include completed"
						aria-label="Filter checklists"
					/>
				</div>
			</div>

			<div
				v-if="configError"
				class="flex flex-1 items-center justify-center px-6 text-center text-sm text-red-600 dark:text-red-400"
			>
				{{ configError }}
			</div>
			<div
				v-else-if="loading"
				class="flex flex-1 items-center justify-center text-sm text-gray-500 dark:text-gray-400"
			>
				Loading…
			</div>
			<div
				v-else-if="!filtered.length"
				class="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center"
			>
				<p class="font-medium text-gray-900 dark:text-gray-100">No checklists</p>
				<p class="max-w-sm text-sm text-gray-500 dark:text-gray-400">
					Create checklists from an Issue or Task in this cockpit.
				</p>
			</div>
			<div v-else class="min-h-0 flex-1 overflow-y-auto">
				<button
					v-for="row in filtered"
					:key="row.name"
					type="button"
					class="block w-full border-b border-gray-100 px-4 py-2.5 text-left hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800"
					:class="{
						'bg-gray-50 shadow-[inset_3px_0_0_0_#111827] dark:bg-gray-800 dark:shadow-[inset_3px_0_0_0_#f3f4f6]':
							row.name === selectedName,
					}"
					@click="openChecklist(row.name)"
				>
					<div class="mb-0.5 flex flex-wrap items-center gap-1.5">
						<Badge
							:theme="statusTheme(row.status)"
							variant="subtle"
							size="sm"
							:label="row.status"
						/>
						<span class="text-[11px] font-semibold tabular-nums text-gray-600 dark:text-gray-400">
							{{ row.done_count || 0 }}/{{ row.total_count || 0 }}
						</span>
					</div>
					<div class="truncate text-sm font-medium text-gray-900 dark:text-gray-100" :title="row.name">
						{{ row.name }}
					</div>
					<div
						v-if="!selectedName && (row.document || row.reference_record)"
						class="mt-0.5 truncate text-xs text-gray-500 dark:text-gray-400"
					>
						{{ row.document }}
						<span v-if="row.reference_record"> / {{ row.reference_record }}</span>
					</div>
				</button>
			</div>
		</section>

		<aside
			v-if="selectedName"
			class="flex w-2/3 min-w-0 flex-none flex-col overflow-y-auto bg-white dark:bg-gray-900"
		>
			<div
				v-if="detailLoading && !selected"
				class="flex flex-1 items-center justify-center text-sm text-gray-500 dark:text-gray-400"
			>
				Loading…
			</div>
			<ChecklistDetail
				v-else-if="selected"
				:checklist="selected"
				@close="closeChecklist"
				@updated="onUpdated"
			/>
		</aside>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Badge, call } from "frappe-ui"
import ChecklistDetail from "@spa/components/ChecklistDetail.vue"
import InboxStatusFilter from "@spa/components/InboxStatusFilter.vue"
import spaConfig from "@/config"

const API = spaConfig.api
const CHECKLIST_API = "phamos.api.checklist_inbox"

const route = useRoute()
const router = useRouter()

const includeCompleted = ref(false)
const search = ref("")
const loading = ref(false)
const configError = ref("")
const rows = ref([])
const selectedName = ref(null)
const selected = ref(null)
const detailLoading = ref(false)

const filtered = computed(() => {
	const q = search.value.trim().toLowerCase()
	if (!q) return rows.value
	return rows.value.filter((r) =>
		[r.name, r.status, r.document, r.reference_record]
			.filter(Boolean)
			.some((v) => String(v).toLowerCase().includes(q))
	)
})

function statusTheme(status) {
	if (status === "Completed") return "green"
	if (status === "In Progress") return "blue"
	return "gray"
}

async function loadInbox() {
	loading.value = true
	configError.value = ""
	try {
		rows.value = await call(`${API}.get_checklists`, {
			include_completed: includeCompleted.value ? 1 : 0,
		})
	} catch (e) {
		configError.value = e?.messages?.[0] || e?.message || "Could not load checklists"
	} finally {
		loading.value = false
	}
}

async function openChecklist(name) {
	selectedName.value = name
	if (route.params.name !== name) {
		router.replace({ name: "ChecklistDetail", params: { name } })
	}
	detailLoading.value = true
	try {
		selected.value = await call(`${CHECKLIST_API}.get_checklist`, { name })
	} finally {
		detailLoading.value = false
	}
}

function closeChecklist() {
	selectedName.value = null
	selected.value = null
	router.replace({ name: "Checklists" })
}

async function onUpdated(checklist) {
	selected.value = checklist
	await loadInbox()
}

watch(includeCompleted, () => loadInbox())

watch(
	() => route.params.name,
	(name) => {
		if (name && name !== selectedName.value) openChecklist(name)
		if (!name) {
			selectedName.value = null
			selected.value = null
		}
	}
)

onMounted(async () => {
	await loadInbox()
	if (route.params.name) {
		await openChecklist(route.params.name)
	}
})
</script>
