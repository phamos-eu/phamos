<template>
	<div class="flex h-full min-h-0 flex-col overflow-y-auto p-5 text-gray-900 dark:text-gray-100">
		<header class="mb-4 flex items-start justify-between gap-3">
			<div>
				<div class="text-xs font-semibold text-gray-500 dark:text-gray-400">{{ issue.name }}</div>
				<h2 class="mt-1 text-lg font-semibold leading-snug text-gray-900 dark:text-gray-100">
					{{ issue.subject }}
				</h2>
			</div>
			<button
				class="rounded-md px-2 py-1 text-xl leading-none text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
				title="Close"
				@click="emit('close')"
			>
				×
			</button>
		</header>

		<section class="mb-5">
			<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
				Status
			</div>
			<div class="flex flex-wrap gap-2">
				<button
					v-for="s in statuses"
					:key="s"
					type="button"
					class="rounded-md border px-2.5 py-1 text-xs font-medium"
					:class="
						status === s
							? 'border-gray-900 bg-gray-900 text-white dark:border-gray-100 dark:bg-gray-100 dark:text-gray-900'
							: 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800'
					"
					:disabled="savingStatus"
					@click="changeStatus(s)"
				>
					{{ s }}
				</button>
			</div>
			<button
				v-if="status === 'Closed'"
				type="button"
				class="mt-2 text-xs text-blue-600 hover:underline dark:text-blue-400"
				:disabled="savingStatus"
				@click="changeStatus('Open')"
			>
				Reopen
			</button>
		</section>

		<section class="mb-5 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
			<div>
				<div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
					Priority
				</div>
				<div>{{ issue.priority || "—" }}</div>
			</div>
			<div>
				<div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
					Issue Type
				</div>
				<div>{{ issue.issue_type || "—" }}</div>
			</div>
			<div>
				<div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
					Created by
				</div>
				<div>{{ issue.owner_name || issue.owner }}</div>
			</div>
			<div>
				<div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
					Department
				</div>
				<div>{{ issue.department || "—" }}</div>
			</div>
			<div>
				<div class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
					Project
				</div>
				<div>{{ issue.project || "—" }}</div>
			</div>
		</section>

		<section class="mb-5">
			<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
				Description
			</div>
			<div
				v-if="issue.description"
				class="prose prose-sm dark:prose-invert max-w-none text-sm text-gray-800 [&_img]:max-w-full [&_img]:rounded-md"
				v-html="issue.description"
			></div>
			<div v-else class="text-sm text-gray-500 dark:text-gray-400">No description</div>
		</section>

		<LinkedChecklistsSection
			document="Issue"
			:reference-record="issue.name"
			:reference-title="issue.subject"
		/>

		<section class="mb-5">
			<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
				Assignees
			</div>
			<div class="mb-3 max-h-48 overflow-y-auto rounded-md border border-gray-200 p-1 dark:border-gray-700">
				<label
					v-for="u in options.users"
					:key="u.name"
					class="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
				>
					<input
						type="checkbox"
						:checked="assignees.includes(u.name)"
						@change="toggleUser(u.name)"
					/>
					<span>{{ u.full_name }}</span>
				</label>
			</div>
			<Button :loading="savingAssignees" @click="saveAssignees">Save assignees</Button>
		</section>

		<footer class="mt-auto border-t border-gray-200 pt-4 dark:border-gray-800">
			<a
				:href="issue.desk_url"
				class="inline-flex rounded-md border border-gray-200 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
			>
				Open in Desk
			</a>
		</footer>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call } from "frappe-ui"
import LinkedChecklistsSection from "./LinkedChecklistsSection.vue"

const props = defineProps({
	issue: { type: Object, required: true },
	options: {
		type: Object,
		default: () => ({ priorities: [], issue_types: [], users: [], chat: {} }),
	},
	apiPrefix: {
		type: String,
		default: "phamos.api.i_own_my_work",
	},
})

const emit = defineEmits(["close", "updated"])

const API = computed(() => props.apiPrefix || "phamos.api.i_own_my_work")
const statuses = ["Open", "On Hold", "Resolved", "Closed"]
const status = ref(props.issue.status)
const assignees = ref([...(props.issue.assignees || [])])
const savingStatus = ref(false)
const savingAssignees = ref(false)

watch(
	() => props.issue,
	(issue) => {
		status.value = issue.status
		assignees.value = [...(issue.assignees || [])]
	},
	{ deep: true }
)

async function changeStatus(next) {
	if (next === props.issue.status) return
	savingStatus.value = true
	try {
		const updated = await call(`${API.value}.update_status`, {
			name: props.issue.name,
			status: next,
		})
		status.value = updated.status
		emit("updated", updated)
	} finally {
		savingStatus.value = false
	}
}

function toggleUser(name) {
	if (assignees.value.includes(name)) {
		assignees.value = assignees.value.filter((u) => u !== name)
	} else {
		assignees.value = [...assignees.value, name]
	}
}

async function saveAssignees() {
	savingAssignees.value = true
	try {
		const updated = await call(`${API.value}.set_assignees`, {
			name: props.issue.name,
			users: assignees.value,
		})
		emit("updated", updated)
	} finally {
		savingAssignees.value = false
	}
}
</script>
