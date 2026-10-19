<template>
	<div class="flex h-full min-h-0 w-full flex-1 flex-col overflow-hidden p-5 text-gray-900 dark:text-gray-100">
		<section class="flex min-h-[50%] flex-1 flex-col">
			<div
				v-if="!chromeHostReady"
				class="mb-2 flex flex-shrink-0 items-center justify-end gap-2"
			>
				<DocSyncBanner :autosave="autosave" />
				<DocViewers :viewers="viewers" />
			</div>
			<div class="flex min-h-0 flex-1 flex-col" :class="{ 'pointer-events-none opacity-80': isClosed }">
				<RichTextField
					:key="issue.name"
					v-model="autosave.draft.description"
					class="flex h-full min-h-0 flex-1 flex-col"
					editor-root-class="flex h-full min-h-0 flex-1 flex-col [&_div:has(>.ProseMirror)]:flex [&_div:has(>.ProseMirror)]:min-h-0 [&_div:has(>.ProseMirror)]:flex-1 [&_div:has(>.ProseMirror)]:flex-col [&_.ProseMirror]:min-h-full [&_.ProseMirror]:flex-1 [&_.ProseMirror]:overflow-y-auto"
					:editable="!isClosed"
					:fixed-menu="editorMenu"
					:locked-by="locks.lockedBy('description')"
					field-label="the description"
					scroll-hint
					placeholder="What needs to be discussed or resolved?"
					editor-class="prose-sm dark:prose-invert max-w-none w-full min-h-full flex-1 px-3 py-2 border border-t-0 border-gray-300 rounded-b-lg bg-white dark:border-gray-600 dark:bg-gray-800"
					@focus="onFieldFocus('description')"
					@blur="onFieldBlur('description')"
				/>
			</div>
			<ErrorMessage class="mt-2 flex-shrink-0" :message="fieldError" />
		</section>
	</div>

	<Teleport v-if="chromeHostReady" to="#cockpit-page-chrome">
		<div class="flex min-w-0 items-center gap-0 pr-3 text-base tracking-tight">
			<span class="flex-shrink-0 font-normal text-gray-500 dark:text-gray-400">{{ issue.name }}:</span>
			<input
				v-if="editingSubject && !isClosed"
				ref="subjectInput"
				v-model="autosave.draft.subject"
				type="text"
				class="ml-1.5 min-w-0 flex-1 border-0 bg-transparent p-0 font-bold tracking-tight text-gray-900 outline-none ring-0 focus:ring-0 dark:text-gray-100"
				placeholder="Subject"
				@keydown.enter.prevent="finishEditSubject"
				@keydown.escape.prevent="cancelEditSubject"
				@blur="finishEditSubject"
			/>
			<button
				v-else
				type="button"
				class="ml-1.5 min-w-0 flex-1 truncate rounded-sm text-left font-bold text-gray-900 dark:text-gray-100"
				:class="isClosed ? 'cursor-default' : 'hover:bg-gray-50 dark:hover:bg-gray-800/60'"
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
				<IssueChatButton :issue-name="issue.name" :subject="issue.subject" :status="status" :api="API" />
			</div>
		</div>
	</Teleport>

	<Teleport v-if="propertiesHostReady" to="#issue-properties-host">
		<div class="flex h-full min-h-0 flex-col bg-surface-white text-ink-gray-9">
			<div class="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-4">
				<section>
					<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
						Status
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
					<FormControl
						v-model="autosave.draft.priority"
						label="Priority"
						type="select"
						size="sm"
						:disabled="isClosed"
						:options="priorityOptions"
					/>
					<FormControl
						v-model="autosave.draft.issue_type"
						label="Issue Type"
						type="select"
						size="sm"
						:disabled="isClosed"
						:options="issueTypeOptions"
					/>
					<FormControl
						v-model="autosave.draft.project"
						label="Project"
						type="select"
						size="sm"
						:disabled="isClosed"
						:options="projectOptions"
					/>
				</section>

				<section>
					<AssigneePicker
						v-model="assignees"
						:assignee-details="assigneeDetails"
						:shortlist-users="options.shortlist_users || []"
						:api-prefix="API"
						:document-name="issue.name"
						:readonly="isClosed"
						method-name="set_assignees"
						@updated="onAssigneesUpdated"
					/>
				</section>
			</div>

			<div class="mt-auto flex-shrink-0 space-y-2 border-t border-outline-gray-2 p-4">
				<div
					v-if="issue.converted_task"
					class="rounded-md border border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-sm"
				>
					<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
						Converted
					</div>
					<button
						type="button"
						class="mt-1 font-medium text-ink-gray-9 hover:underline"
						@click="goToConvertedTask"
					>
						Open {{ issue.converted_task }}
					</button>
				</div>
				<Button
					v-else-if="!isClosed"
					class="w-full"
					variant="solid"
					@click="showConvert = true"
				>
					Convert to Task
				</Button>
				<p class="text-xs text-ink-gray-6">
					Created by {{ issue.owner_name || issue.owner }}
					<span v-if="issue.department"> · {{ issue.department }}</span>
				</p>
				<a
					:href="issue.desk_url"
					class="flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm font-medium text-ink-gray-7 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				>
					<FeatherIcon name="external-link" class="h-4 w-4 flex-shrink-0" />
					<span class="truncate">Open in Desk</span>
				</a>
			</div>
		</div>
	</Teleport>

	<ConvertToTaskDialog
		v-model="showConvert"
		:issue="issue"
		:options="options"
		:api-prefix="API"
		@converted="onConverted"
	/>

	<Dialog
		v-model="showPostConvertChoice"
		:options="{
			title: 'Converted to Task',
			size: '3xl',
			actions: [
				{
					label: 'Issue list',
					variant: 'subtle',
					onClick: goToIssueListAfterConvert,
				},
				{
					label: 'Open Task Gantt',
					variant: 'solid',
					onClick: goToTaskAfterConvert,
				},
			],
		}"
	>
		<template #body-content>
			<div class="space-y-4">
				<p class="text-sm text-ink-gray-7">
					Issue
					<span class="font-medium text-ink-gray-9">{{ issue.name }}</span>
					is now Task
					<span class="font-semibold text-ink-gray-9">{{ postConvertTaskName }}</span>.
					Where do you want to go next?
				</p>
				<SchedulePreview
					v-if="showPostConvertChoice && postConvertTaskName"
					:highlight-task-id="postConvertTaskName"
					:api-prefix="API"
					@open="goToTaskAfterConvert"
				/>
			</div>
		</template>
	</Dialog>

	<Dialog
		v-model="showConvertedNotice"
		:options="{
			title: 'Issue converted to Task',
			size: '3xl',
			actions: [],
		}"
	>
		<template #body-content>
			<div class="space-y-4">
				<p class="text-sm text-ink-gray-7">
					This Issue was converted to Task
					<button
						type="button"
						class="font-semibold text-ink-gray-9 underline-offset-2 hover:underline"
						@click="openConvertedFromNotice"
					>
						{{ issue.converted_task }}
					</button>
					and is now closed. Fields are read-only while the Issue stays Closed.
				</p>
				<SchedulePreview
					v-if="showConvertedNotice && issue.converted_task"
					:highlight-task-id="issue.converted_task"
					:api-prefix="API"
					@open="openConvertedFromNotice"
				/>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { call, Dialog, FeatherIcon, toast, Badge } from "frappe-ui"
import AssigneePicker from "@spa/components/AssigneePicker.vue"
import DocSyncBanner from "@spa/components/DocSyncBanner.vue"
import DocViewers from "@spa/components/DocViewers.vue"
import IssueChatButton from "@spa/components/IssueChatButton.vue"
import RichTextField from "@spa/components/RichTextField.vue"
import { useAutosaveDoc } from "@spa/composables/useAutosaveDoc.js"
import { useDocRealtime } from "@spa/composables/useDocRealtime.js"
import { useFieldLocks } from "@spa/composables/useFieldLocks.js"
import { lockExplanation, lockHeadline, lockMessage } from "@spa/utils/fieldLockText.js"
import ConvertToTaskDialog from "@spa/components/ConvertToTaskDialog.vue"
import SchedulePreview from "@spa/components/SchedulePreview.vue"
import { setPageChromeActive } from "@spa/pageChrome.js"
import spaConfig from "@/config"

const props = defineProps({
	issue: { type: Object, required: true },
	options: {
		type: Object,
		default: () => ({
			priorities: [],
			issue_types: [],
			shortlist_users: [],
			projects: [],
		}),
	},
	apiPrefix: {
		type: String,
		default: "",
	},
})

const emit = defineEmits(["close", "updated", "converted"])

const router = useRouter()
const API = computed(() => props.apiPrefix || spaConfig.api)
const propertiesHostReady = ref(false)
const chromeHostReady = ref(false)
const showConvert = ref(false)
const showConvertedNotice = ref(false)
const showPostConvertChoice = ref(false)
const postConvertTaskName = ref("")
const isClosed = computed(() => (status.value || props.issue.status) === "Closed")
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
	"Separator",
	"Image",
]
const statuses = ["Open", "Replied", "On Hold", "Resolved", "Closed"]

function statusTheme(status) {
	const map = {
		Open: "red",
		Replied: "blue",
		"On Hold": "orange",
		Resolved: "green",
		Closed: "gray",
	}
	return map[status] || "blue"
}

function statusStrongClass(status) {
	const map = {
		Open: "bg-red-600 text-white dark:bg-red-500",
		Replied: "bg-blue-600 text-white dark:bg-blue-500",
		"On Hold": "bg-amber-500 text-white dark:bg-amber-500",
		Resolved: "bg-green-600 text-white dark:bg-green-500",
		Closed: "bg-gray-700 text-white dark:bg-gray-500",
	}
	return map[status] || "bg-blue-600 text-white dark:bg-blue-500"
}

const status = ref(props.issue.status)
const assignees = ref([...(props.issue.assignees || [])])
const savingStatus = ref(false)
const editingSubject = ref(false)
const subjectInput = ref(null)

// Editable fields live in the autosave draft; server payloads (save responses,
// parent reloads, realtime refreshes) never overwrite a field being edited.
const autosave = useAutosaveDoc({
	doc: () => props.issue,
	fields: {
		subject: { kind: "text", trim: true, required: true, label: "Subject" },
		description: { kind: "html", label: "Description" },
		priority: { kind: "select", immediate: true, label: "Priority" },
		issue_type: { kind: "select", immediate: true, label: "Issue Type" },
		project: { kind: "select", immediate: true, label: "Project" },
	},
	request: (name, payload, modified) => ({
		method: `${API.value}.update_issue`,
		args: { name, ...payload, modified },
	}),
	fetch: (name) => call(`${API.value}.get_issue`, { name }),
	readonly: () => isClosed.value,
	onSaved: (issue) => emit("updated", issue),
	onRemoteApplied: (issue) => emit("updated", issue),
	onError: (message) => toast({ title: message, icon: "x-circle", iconClasses: "text-ink-red-4" }),
})

const fieldError = computed(() => (autosave.status === "error" ? autosave.error : ""))

const realtime = useDocRealtime({
	doctype: "Issue",
	name: () => props.issue.name,
	onDocUpdate: (modified) => autosave.noteRemoteModified(modified),
})
const viewers = realtime.viewers

const locks = useFieldLocks({
	doctype: "Issue",
	name: () => props.issue.name,
	realtime,
	enabled: () => !isClosed.value,
	onReleased: () => {
		if (autosave.status === "blocked") autosave.flush()
	},
})
const subjectLock = computed(() => locks.lockedBy("subject"))

async function onFieldFocus(field) {
	autosave.setFocused(field, true)
	if (!isClosed.value) await locks.acquire(field)
}

async function onFieldBlur(field) {
	const docname = props.issue.name
	// Release the lock only once the server has everything typed in the field.
	await autosave.setFocused(field, false)
	locks.release(field, { docname })
}

async function startEditSubject() {
	if (isClosed.value) return
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

const assigneeDetails = computed(() => {
	const names = props.issue.assignees || []
	const labels = props.issue.assignee_names || []
	const images = props.issue.assignee_images || []
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

const issueTypeOptions = computed(() => [
	{ label: "—", value: "" },
	...(props.options.issue_types || []).map((t) => ({ label: t, value: t })),
])

const projectOptions = computed(() => [
	{ label: "—", value: "" },
	...(props.options.projects || []).map((p) => ({
		label: p.project_name || p.name,
		value: p.name,
	})),
])

async function syncPropertiesHost() {
	await nextTick()
	propertiesHostReady.value = !!document.getElementById("issue-properties-host")
	chromeHostReady.value = !!document.getElementById("cockpit-page-chrome")
	if (chromeHostReady.value) setPageChromeActive(true)
}

onMounted(syncPropertiesHost)

onBeforeUnmount(() => {
	setPageChromeActive(false)
})

watch(
	() => props.issue,
	(issue) => {
		// Status and assignees are saved by their own endpoints and not
		// autosaved, so they always follow the server.
		status.value = issue.status
		assignees.value = [...(issue.assignees || [])]
		syncPropertiesHost()
	},
	{ deep: true }
)

watch(
	() => props.issue.name,
	() => {
		editingSubject.value = false
	}
)

watch(
	() => props.issue?.name,
	() => {
		const issue = props.issue
		// Skip reopen notice while the post-convert destination prompt is open.
		if (showPostConvertChoice.value) {
			showConvertedNotice.value = false
			return
		}
		if (issue?.converted_task && issue.status === "Closed") {
			showConvertedNotice.value = true
		} else {
			showConvertedNotice.value = false
		}
	},
	{ immediate: true }
)

async function changeStatus(next) {
	if (next === props.issue.status) return
	savingStatus.value = true
	try {
		// Save pending text first: a Closed issue is read-only afterwards.
		await autosave.flush()
		const updated = await call(`${API.value}.update_status`, {
			name: props.issue.name,
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

function goToConvertedTask() {
	const name = props.issue.converted_task || postConvertTaskName.value
	if (!name) return
	router.push({ name: "TaskDetail", params: { name } })
}

function openConvertedFromNotice() {
	showConvertedNotice.value = false
	goToConvertedTask()
}

function goToTaskAfterConvert() {
	const name = postConvertTaskName.value
	showPostConvertChoice.value = false
	if (!name) return
	router.push({ name: "TaskDetail", params: { name } })
}

function goToIssueListAfterConvert() {
	showPostConvertChoice.value = false
	postConvertTaskName.value = ""
	emit("close")
}

defineExpose({ flush: () => autosave.flush() })

function onConverted(result) {
	const task = result?.task
	postConvertTaskName.value = task?.name || ""
	showConvertedNotice.value = false
	showPostConvertChoice.value = true
	emit("converted", result)
	toast({
		title: task?.name ? `Converted to ${task.name}` : "Converted to Task",
		icon: "check-circle",
		iconClasses: "text-ink-green-4",
	})
}
</script>
