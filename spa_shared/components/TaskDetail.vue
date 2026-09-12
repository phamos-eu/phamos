<template>
	<div class="flex h-full min-h-0 flex-col bg-surface-white text-ink-gray-9 dark:bg-surface-gray-1">
		<Teleport v-if="chromeHostReady" to="#cockpit-page-chrome">
			<div class="flex min-w-0 items-center gap-0 pr-3 text-base tracking-tight">
				<span class="flex-shrink-0 font-normal text-ink-gray-5">{{ task.name }}:</span>
				<input
					v-if="editingSubject"
					ref="subjectInput"
					v-model="subject"
					type="text"
					class="ml-1.5 min-w-0 flex-1 border-0 bg-transparent p-0 font-bold tracking-tight text-ink-gray-9 outline-none ring-0 focus:ring-0"
					placeholder="Subject"
					@keydown.enter.prevent="finishEditSubject"
					@keydown.escape.prevent="cancelEditSubject"
					@blur="finishEditSubject"
				/>
				<button
					v-else
					type="button"
					class="ml-1.5 min-w-0 flex-1 truncate rounded-sm text-left font-bold text-ink-gray-9 hover:bg-surface-gray-2"
					@click="startEditSubject"
				>
					{{ subject.trim() || "Untitled" }}
				</button>
			</div>
		</Teleport>

		<div class="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-4">
			<section>
				<div class="mb-2 flex items-center justify-between gap-2">
					<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
						Status
					</div>
					<button
						type="button"
						class="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-9"
						aria-label="Close"
						@click="emit('close')"
					>
						<FeatherIcon name="x" class="h-4 w-4" />
					</button>
				</div>
				<div class="flex flex-wrap items-center gap-2.5">
					<button
						v-for="s in statuses"
						:key="s"
						type="button"
						class="rounded-full disabled:opacity-50"
						:class="
							status === s
								? 'origin-center scale-[1.2] z-[1]'
								: 'opacity-70 hover:opacity-100'
						"
						:disabled="savingStatus"
						@click="changeStatus(s)"
					>
						<span
							v-if="status === s"
							class="inline-flex h-5 items-center rounded-full px-1.5 text-xs font-semibold"
							:class="statusStrongClass(s)"
						>
							{{ s }}
						</span>
						<Badge
							v-else
							:label="s"
							:theme="statusTheme(s)"
							size="sm"
							variant="subtle"
						/>
					</button>
				</div>
			</section>

			<section class="space-y-3">
				<div class="w-full">
					<label class="mb-1.5 block text-xs text-ink-gray-5">Description</label>
					<TextEditor
						:content="description"
						:fixed-menu="editorMenu"
						placeholder="Task details…"
						editor-class="prose-sm dark:prose-invert max-w-none w-full min-h-[120px] max-h-[240px] overflow-y-auto px-3 py-2 border border-t-0 border-outline-gray-2 rounded-b-lg bg-surface-white dark:bg-surface-gray-2"
						@change="(html) => (description = html)"
					/>
				</div>
				<FormControl
					v-model="priority"
					label="Priority"
					type="select"
					size="sm"
					:options="priorityOptions"
				/>
				<FormControl
					v-model="project"
					label="Project"
					type="select"
					size="sm"
					:options="projectOptions"
				/>
				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Expected start</label>
					<DatePicker
						v-model="expStartDate"
						placeholder="Start date"
						class="w-full"
						:formatter="formatDate"
					/>
				</div>
				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Expected end</label>
					<DatePicker
						v-model="expEndDate"
						placeholder="End date"
						class="w-full"
						:formatter="formatDate"
					/>
				</div>
				<div>
					<div class="mb-1.5 flex items-center justify-between gap-2">
						<label class="text-xs text-ink-gray-5" for="task-progress">Progress</label>
						<span class="text-xs font-medium tabular-nums text-ink-gray-7">
							{{ progressLabel }}%
						</span>
					</div>
					<input
						id="task-progress"
						v-model.number="progress"
						type="range"
						min="0"
						max="100"
						step="1"
						class="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-surface-gray-3"
						style="accent-color: var(--ink-blue-3)"
					/>
				</div>
				<ErrorMessage :message="fieldError" />
			</section>

			<section v-if="task.issue">
				<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
					From Issue
				</div>
				<button
					type="button"
					class="mt-1 text-sm font-medium text-ink-gray-9 underline-offset-2 hover:underline"
					@click="goToSourceIssue"
				>
					{{ task.issue }}
				</button>
			</section>

			<LinkedChecklistsSection
				document="Task"
				:reference-record="task.name"
				:reference-title="subject || task.subject"
			/>

			<section>
				<AssigneePicker
					v-model="assignees"
					:assignee-details="assigneeDetails"
					:shortlist-users="options.shortlist_users || []"
					:api-prefix="API"
					:document-name="task.name"
					method-name="set_task_assignees"
					@updated="onAssigneesUpdated"
				/>
			</section>
		</div>

		<div class="mt-auto flex-shrink-0 space-y-2 border-t border-outline-gray-2 p-4">
			<p class="text-xs text-ink-gray-6">
				Created by {{ task.owner_name || task.owner || "—" }}
				<span v-if="task.department"> · {{ task.department }}</span>
			</p>
			<a
				:href="task.desk_url"
				class="flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm font-medium text-ink-gray-7 hover:bg-surface-gray-2 hover:text-ink-gray-9"
			>
				<FeatherIcon name="external-link" class="h-4 w-4 flex-shrink-0" />
				<span class="truncate">Open in Desk</span>
			</a>
		</div>
	</div>
</template>

<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { Badge, call, DatePicker, debounce, TextEditor, toast } from "frappe-ui"
import AssigneePicker from "@spa/components/AssigneePicker.vue"
import LinkedChecklistsSection from "@spa/components/LinkedChecklistsSection.vue"
import { formatDate } from "@spa/utils/datetime.js"
import { setPageChromeActive } from "@spa/pageChrome.js"
import spaConfig from "@/config"

const props = defineProps({
	task: { type: Object, required: true },
	options: {
		type: Object,
		default: () => ({ priorities: [], shortlist_users: [], projects: [] }),
	},
	apiPrefix: {
		type: String,
		default: "",
	},
})

const emit = defineEmits(["close", "updated"])

const router = useRouter()
const API = computed(() => props.apiPrefix || spaConfig.api)
const statuses = ["Open", "Working", "Pending Review", "Overdue", "Completed"]
const editorMenu = [
	"Paragraph",
	"Heading 2",
	"Heading 3",
	"Separator",
	"Bold",
	"Italic",
	"Link",
	"Separator",
	"Bullet List",
	"Numbered List",
]

const chromeHostReady = ref(false)
const status = ref(props.task.status)
const subject = ref(props.task.subject || "")
const description = ref(props.task.description || "")
const priority = ref(props.task.priority || "")
const project = ref(props.task.project || "")
const expStartDate = ref(props.task.exp_start_date || "")
const expEndDate = ref(props.task.exp_end_date || "")
const progress = ref(Number(props.task.progress ?? 0))
const assignees = ref([...(props.task.assignees || [])])
const savingStatus = ref(false)
const savingFields = ref(false)
const fieldError = ref("")
const syncing = ref(false)
const editingSubject = ref(false)
const subjectInput = ref(null)
const subjectBeforeEdit = ref("")

const progressLabel = computed(() =>
	Math.min(100, Math.max(0, Math.round(Number(progress.value) || 0)))
)

function statusTheme(s) {
	const map = {
		Open: "blue",
		Working: "orange",
		"Pending Review": "orange",
		Overdue: "red",
		Completed: "green",
	}
	return map[s] || "gray"
}

function statusStrongClass(s) {
	const map = {
		Open: "bg-blue-600 text-white dark:bg-blue-500",
		Working: "bg-amber-500 text-white dark:bg-amber-500",
		"Pending Review": "bg-orange-500 text-white dark:bg-orange-500",
		Overdue: "bg-red-600 text-white dark:bg-red-500",
		Completed: "bg-green-600 text-white dark:bg-green-500",
	}
	return map[s] || "bg-gray-700 text-white dark:bg-gray-500"
}

const assigneeDetails = computed(() => {
	const names = props.task.assignees || []
	const labels = props.task.assignee_names || []
	const images = props.task.assignee_images || []
	return names.map((name, i) => ({
		name,
		full_name: labels[i] || name,
		user_image: images[i] || "",
	}))
})

const priorityOptions = computed(() => [
	{ label: "—", value: "" },
	...(props.options.priorities || []).map((p) => ({ label: p, value: p })),
])

const projectOptions = computed(() => [
	{ label: "—", value: "" },
	...(props.options.projects || []).map((p) => ({
		label: p.project_name || p.name,
		value: p.name,
	})),
])

async function syncChromeHost() {
	await nextTick()
	chromeHostReady.value = !!document.getElementById("cockpit-page-chrome")
	if (chromeHostReady.value) setPageChromeActive(true)
}

async function startEditSubject() {
	subjectBeforeEdit.value = subject.value
	editingSubject.value = true
	await nextTick()
	subjectInput.value?.focus?.()
}

function finishEditSubject() {
	if (!editingSubject.value) return
	editingSubject.value = false
	if (!subject.value.trim()) {
		subject.value = subjectBeforeEdit.value || props.task.subject || ""
	}
}

function cancelEditSubject() {
	subject.value = subjectBeforeEdit.value
	editingSubject.value = false
}

onMounted(syncChromeHost)

onBeforeUnmount(() => {
	setPageChromeActive(false)
})

watch(
	() => props.task,
	(task) => {
		syncing.value = true
		status.value = task.status
		subject.value = task.subject || ""
		description.value = task.description || ""
		priority.value = task.priority || ""
		project.value = task.project || ""
		expStartDate.value = task.exp_start_date || ""
		expEndDate.value = task.exp_end_date || ""
		progress.value = Number(task.progress ?? 0)
		assignees.value = [...(task.assignees || [])]
		fieldError.value = ""
		editingSubject.value = false
		nextTick(() => {
			syncing.value = false
		})
		syncChromeHost()
	},
	{ deep: true }
)

function isEmptyHtml(html) {
	if (!html) return true
	const text = String(html)
		.replace(/<img[^>]*>/gi, "img")
		.replace(/<[^>]+>/g, "")
		.replace(/&nbsp;/g, " ")
		.trim()
	return !text
}

function normalizedDescription() {
	return isEmptyHtml(description.value) ? "" : description.value
}

function fieldsDirty() {
	const task = props.task
	return (
		subject.value.trim() !== (task.subject || "").trim() ||
		normalizedDescription() !== (task.description || "") ||
		(priority.value || "") !== (task.priority || "") ||
		(project.value || "") !== (task.project || "") ||
		String(expStartDate.value || "") !== String(task.exp_start_date || "") ||
		String(expEndDate.value || "") !== String(task.exp_end_date || "") ||
		Number(progress.value || 0) !== Number(task.progress ?? 0)
	)
}

async function saveFields() {
	if (syncing.value || savingFields.value) return
	if (!subject.value.trim()) {
		fieldError.value = "Subject is required"
		return
	}
	if (!fieldsDirty()) return

	fieldError.value = ""
	savingFields.value = true
	try {
		const updated = await call(`${API.value}.update_task`, {
			name: props.task.name,
			subject: subject.value.trim(),
			description: normalizedDescription(),
			priority: priority.value || "",
			project: project.value || "",
			exp_start_date: expStartDate.value || "",
			exp_end_date: expEndDate.value || "",
			progress: progressLabel.value,
		})
		emit("updated", updated)
	} catch (e) {
		fieldError.value = e?.messages?.[0] || e?.message || "Could not save task"
		toast.error(fieldError.value)
	} finally {
		savingFields.value = false
	}
}

const scheduleSave = debounce(() => {
	saveFields()
}, 500)

watch([subject, description, priority, project, expStartDate, expEndDate, progress], () => {
	if (syncing.value) return
	scheduleSave()
})

async function changeStatus(next) {
	if (next === props.task.status) return
	savingStatus.value = true
	try {
		const updated = await call(`${API.value}.update_task_status`, {
			name: props.task.name,
			status: next,
		})
		status.value = updated.status
		emit("updated", updated)
	} catch (e) {
		toast.error(e?.messages?.[0] || e?.message || "Could not update status")
	} finally {
		savingStatus.value = false
	}
}

function onAssigneesUpdated(updated) {
	assignees.value = [...(updated.assignees || [])]
	emit("updated", updated)
}

function goToSourceIssue() {
	const name = props.task.issue
	if (!name) return
	router.push({ name: "IssueDetail", params: { name } })
}
</script>
