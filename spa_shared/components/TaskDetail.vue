<template>
	<div class="flex h-full min-h-0 flex-col bg-surface-white text-ink-gray-9 dark:bg-surface-gray-1">
		<Teleport v-if="chromeHostReady" to="#cockpit-page-chrome">
			<div class="flex min-w-0 items-center gap-0 pr-3 text-base tracking-tight">
				<span class="flex-shrink-0 font-normal text-ink-gray-5">{{ task.name }}:</span>
				<input
					v-if="editingSubject"
					ref="subjectInput"
					v-model="autosave.draft.subject"
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
					:title="subjectLock ? lockMessage(subjectLock, 'the subject') : ''"
					@click="startEditSubject"
				>
					<FeatherIcon
						v-if="subjectLock"
						name="lock"
						class="mr-1 inline h-3.5 w-3.5 align-[-2px] text-ink-amber-3"
					/>
					{{ autosave.draft.subject.trim() || "Untitled" }}
				</button>
				<div class="ml-auto flex flex-shrink-0 items-center gap-2 pl-3">
					<DocSyncBanner :autosave="autosave" />
					<DocViewers :viewers="viewers" />
				</div>
			</div>
		</Teleport>

		<div class="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-4">
			<div v-if="!chromeHostReady" class="flex items-center justify-end gap-2">
				<DocSyncBanner :autosave="autosave" />
				<DocViewers :viewers="viewers" />
			</div>
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
					<RichTextField
						:key="task.name"
						v-model="autosave.draft.description"
						:fixed-menu="editorMenu"
						:locked-by="locks.lockedBy('description')"
					field-label="the description"
						placeholder="Task details…"
						editor-class="prose-sm dark:prose-invert max-w-none w-full min-h-[120px] max-h-[240px] overflow-y-auto px-3 py-2 border border-t-0 border-outline-gray-2 rounded-b-lg bg-surface-white dark:bg-surface-gray-2"
						@focus="onFieldFocus('description')"
						@blur="onFieldBlur('description')"
					/>
				</div>
				<FormControl
					v-model="autosave.draft.priority"
					label="Priority"
					type="select"
					size="sm"
					:options="priorityOptions"
				/>
				<FormControl
					v-model="autosave.draft.project"
					label="Project"
					type="select"
					size="sm"
					:options="projectOptions"
				/>
				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Task Owner</label>
					<FrappeLink
						v-model="autosave.draft.custom_task_owner"
						doctype="User"
						:filters="{ enabled: 1 }"
						placeholder="Who is responsible"
					/>
				</div>
				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Expected start</label>
					<DatePicker
						v-model="autosave.draft.exp_start_date"
						placeholder="Start date"
						class="w-full"
						:formatter="formatDate"
					/>
				</div>
				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Expected end</label>
					<DatePicker
						v-model="autosave.draft.exp_end_date"
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
						v-model.number="autosave.draft.progress"
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
				:reference-title="autosave.draft.subject || task.subject"
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
				target="_blank"
				rel="noopener noreferrer"
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
import { Badge, call, DatePicker, FeatherIcon, toast } from "frappe-ui"
import AssigneePicker from "@spa/components/AssigneePicker.vue"
import DocSyncBanner from "@spa/components/DocSyncBanner.vue"
import DocViewers from "@spa/components/DocViewers.vue"
import FrappeLink from "@spa/components/FrappeLink.vue"
import RichTextField from "@spa/components/RichTextField.vue"
import { useAutosaveDoc } from "@spa/composables/useAutosaveDoc.js"
import { useDocRealtime } from "@spa/composables/useDocRealtime.js"
import { useFieldLocks } from "@spa/composables/useFieldLocks.js"
import { lockExplanation, lockHeadline, lockMessage } from "@spa/utils/fieldLockText.js"
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
const assignees = ref([...(props.task.assignees || [])])
const savingStatus = ref(false)
const editingSubject = ref(false)
const subjectInput = ref(null)

function clampProgress(value) {
	return Math.min(100, Math.max(0, Math.round(Number(value) || 0)))
}

// Editable fields live in the autosave draft; server payloads (save responses,
// Gantt drags, realtime refreshes) never overwrite a field being edited.
const autosave = useAutosaveDoc({
	doc: () => props.task,
	fields: {
		subject: { kind: "text", trim: true, required: true, label: "Subject" },
		description: { kind: "html", label: "Description" },
		priority: { kind: "select", immediate: true, label: "Priority" },
		project: { kind: "select", immediate: true, label: "Project" },
		custom_task_owner: { kind: "select", immediate: true, label: "Task Owner" },
		exp_start_date: { kind: "date", immediate: true, label: "Expected start" },
		exp_end_date: { kind: "date", immediate: true, label: "Expected end" },
		progress: { kind: "number", toServer: clampProgress, label: "Progress" },
	},
	request: (name, payload, modified) => ({
		method: `${API.value}.update_task`,
		args: { name, ...payload, modified },
	}),
	fetch: (name) => call(`${API.value}.get_task`, { name }),
	onSaved: (task) => emit("updated", task),
	onRemoteApplied: (task) => emit("updated", task),
	onError: (message) => toast({ title: message, icon: "x-circle", iconClasses: "text-ink-red-4" }),
})

const fieldError = computed(() => (autosave.status === "error" ? autosave.error : ""))
const progressLabel = computed(() => clampProgress(autosave.draft.progress))

const realtime = useDocRealtime({
	doctype: "Task",
	name: () => props.task.name,
	onDocUpdate: (modified) => autosave.noteRemoteModified(modified),
})
const viewers = realtime.viewers

const locks = useFieldLocks({
	doctype: "Task",
	name: () => props.task.name,
	realtime,
	onReleased: () => {
		if (autosave.status === "blocked") autosave.flush()
	},
})
const subjectLock = computed(() => locks.lockedBy("subject"))

async function onFieldFocus(field) {
	autosave.setFocused(field, true)
	await locks.acquire(field)
}

async function onFieldBlur(field) {
	const docname = props.task.name
	// Release the lock only once the server has everything typed in the field.
	await autosave.setFocused(field, false)
	locks.release(field, { docname })
}

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
	if (subjectLock.value) {
		toast({
			title: lockHeadline(subjectLock.value, "the subject"),
			text: lockExplanation(subjectLock.value),
			icon: "lock",
			iconClasses: "text-ink-amber-3",
		})
		return
	}
	autosave.setFocused("subject", true)
	// Two people can click the subject at the same moment; only the one who
	// gets the lock may edit it.
	if (!(await locks.acquire("subject"))) {
		autosave.setFocused("subject", false)
		if (subjectLock.value) {
			toast({
				title: lockHeadline(subjectLock.value, "the subject"),
				text: lockExplanation(subjectLock.value),
				icon: "lock",
				iconClasses: "text-ink-amber-3",
			})
		}
		return
	}
	editingSubject.value = true
	await nextTick()
	subjectInput.value?.focus?.()
}

function finishEditSubject() {
	if (!editingSubject.value) return
	editingSubject.value = false
	if (!autosave.draft.subject.trim()) autosave.revert("subject")
	onFieldBlur("subject")
}

function cancelEditSubject() {
	autosave.revert("subject")
	editingSubject.value = false
	onFieldBlur("subject")
}

onMounted(syncChromeHost)

onBeforeUnmount(() => {
	setPageChromeActive(false)
})

watch(
	() => props.task,
	(task) => {
		// Status and assignees are saved by their own endpoints and always
		// follow the server.
		status.value = task.status
		assignees.value = [...(task.assignees || [])]
		syncChromeHost()
	},
	{ deep: true }
)

watch(
	() => props.task.name,
	() => {
		editingSubject.value = false
	}
)

async function changeStatus(next) {
	if (next === props.task.status) return
	savingStatus.value = true
	try {
		await autosave.flush()
		const updated = await call(`${API.value}.update_task_status`, {
			name: props.task.name,
			status: next,
		})
		status.value = updated.status
		emit("updated", updated)
	} catch (e) {
		toast({
			title: e?.messages?.[0] || e?.message || "Could not update status",
			icon: "x-circle",
			iconClasses: "text-ink-red-4",
		})
	} finally {
		savingStatus.value = false
	}
}

function onAssigneesUpdated(updated) {
	assignees.value = [...(updated.assignees || [])]
	emit("updated", updated)
}

defineExpose({ flush: () => autosave.flush() })

function goToSourceIssue() {
	const name = props.task.issue
	if (!name) return
	router.push({ name: "IssueDetail", params: { name } })
}
</script>
