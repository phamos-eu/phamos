<template>
	<div class="flex h-full min-h-0">
		<section
			class="flex min-w-0 flex-col border-r border-gray-200 bg-white"
			:class="selectedName ? 'w-[15%] flex-none' : 'flex-1'"
		>
			<div
				class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-4 py-3"
			>
				<label class="flex items-center gap-2 text-sm text-gray-600">
					<input v-model="includeCompleted" type="checkbox" class="rounded border-gray-300" />
					Show completed
				</label>
				<input
					v-model="search"
					type="search"
					placeholder="Search…"
					class="h-8 min-w-0 flex-1 rounded-md border border-gray-300 px-2 text-sm"
					:class="selectedName ? 'max-w-full' : 'max-w-xs'"
				/>
			</div>

			<div v-if="loading" class="flex flex-1 items-center justify-center text-sm text-gray-500">
				Loading…
			</div>
			<div
				v-else-if="!filtered.length"
				class="flex flex-1 flex-col items-center justify-center gap-2 px-4 text-center"
			>
				<p class="font-medium text-gray-900">No checklists</p>
				<p class="text-sm text-gray-500">Create checklists from an Issue or in Desk.</p>
			</div>
			<div v-else class="min-h-0 flex-1 overflow-y-auto">
				<button
					v-for="row in filtered"
					:key="row.name"
					type="button"
					class="block w-full border-b border-gray-100 px-3 py-2.5 text-left hover:bg-gray-50"
					:class="{
						'bg-gray-50 shadow-[inset_3px_0_0_0_#111827]': row.name === selectedName,
					}"
					@click="openChecklist(row.name)"
				>
					<div class="mb-0.5 flex flex-wrap items-center gap-1.5">
						<span
							class="rounded-full px-1.5 py-0.5 text-[10px] font-semibold"
							:class="statusClass(row.status)"
						>
							{{ row.status }}
						</span>
						<span class="text-[11px] font-semibold tabular-nums text-gray-600">
							{{ row.done_count || 0 }}/{{ row.total_count || 0 }}
						</span>
					</div>
					<div
						class="truncate text-sm font-medium text-gray-900"
						:title="row.name"
					>
						{{ row.name }}
					</div>
					<div
						v-if="!selectedName && (row.document || row.reference_record)"
						class="mt-0.5 truncate text-xs text-gray-500"
					>
						{{ row.document }}
						<span v-if="row.reference_record"> / {{ row.reference_record }}</span>
					</div>
				</button>
			</div>
		</section>

		<aside
			v-if="selectedName"
			class="flex min-w-0 flex-1 flex-col bg-white md:flex-row"
		>
			<div
				class="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto"
				:class="{ 'md:border-r md:border-gray-200': showChatColumn }"
			>
				<div
					v-if="detailLoading && !selected"
					class="flex flex-1 items-center justify-center text-sm text-gray-500"
				>
					Loading…
				</div>
				<ChecklistDetail
					v-else-if="selected"
					:checklist="selected"
					@close="closeChecklist"
					@updated="onUpdated"
				/>
			</div>

			<div
				v-if="showChatColumn && selected"
				class="flex min-h-[280px] min-w-0 flex-1 flex-col border-t border-gray-200 md:min-h-0 md:border-l md:border-t-0"
			>
				<IssueChat
					:document-name="selected.name"
					linked-doctype="Checklist"
					:chat-flags="chatFlags"
				/>
			</div>
		</aside>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call } from "frappe-ui"
import ChecklistDetail from "../components/ChecklistDetail.vue"
import IssueChat from "../components/IssueChat.vue"

const API = "phamos.api.i_own_my_work"

const route = useRoute()
const router = useRouter()

const includeCompleted = ref(false)
const search = ref("")
const loading = ref(false)
const rows = ref([])
const selectedName = ref(null)
const selected = ref(null)
const detailLoading = ref(false)
const chatFlags = ref({
	raven_installed: false,
	enabled: false,
	raven_unavailable: true,
})

const showChatColumn = computed(() => !!chatFlags.value.raven_installed)

const filtered = computed(() => {
	const q = search.value.trim().toLowerCase()
	if (!q) return rows.value
	return rows.value.filter((r) =>
		[r.name, r.status, r.document, r.reference_record]
			.filter(Boolean)
			.some((v) => String(v).toLowerCase().includes(q))
	)
})

function statusClass(status) {
	const map = {
		"Not Started": "bg-gray-100 text-gray-600",
		"In Progress": "bg-blue-50 text-blue-700",
		Completed: "bg-emerald-50 text-emerald-700",
	}
	return map[status] || map["Not Started"]
}

async function loadFlags() {
	try {
		const opts = await call(`${API}.get_form_options`)
		chatFlags.value = opts.chat || chatFlags.value
	} catch (e) {
		try {
			chatFlags.value = await call(`${API}.get_chat_settings`)
		} catch (e2) {
			/* leave defaults */
		}
	}
}

async function loadInbox() {
	loading.value = true
	try {
		rows.value = await call(`${API}.get_checklist_inbox`, {
			include_completed: includeCompleted.value ? 1 : 0,
		})
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
		selected.value = await call(`${API}.get_checklist`, { name })
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
	await Promise.all([loadFlags(), loadInbox()])
	if (route.params.name) {
		await openChecklist(route.params.name)
	}
})
</script>
