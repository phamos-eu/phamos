<template>
	<div class="flex h-full min-h-0 w-full flex-1 flex-col overflow-hidden p-5 text-gray-900 dark:text-gray-100">
		<section class="flex min-h-[50%] flex-1 flex-col">
			<label class="mb-1.5 block flex-shrink-0 text-xs text-ink-gray-5">Description</label>
			<div class="flex min-h-0 flex-1 flex-col">
				<TextEditor
					class="flex h-full min-h-0 flex-1 flex-col [&]:h-full [&_.ProseMirror]:min-h-full [&_.ProseMirror]:flex-1 [&_.ProseMirror]:overflow-y-auto"
					:content="description"
					:fixed-menu="editorMenu"
					placeholder="What needs to be discussed or resolved?"
					editor-class="prose-sm dark:prose-invert max-w-none w-full min-h-full flex-1 px-3 py-2 border border-t-0 border-gray-300 rounded-b-lg bg-white dark:border-gray-600 dark:bg-gray-800"
					@change="(html) => (description = html)"
				/>
			</div>
			<ErrorMessage class="mt-2 flex-shrink-0" :message="fieldError" />
		</section>
	</div>

	<Teleport v-if="chromeHostReady" to="#cockpit-page-chrome">
		<div class="flex min-w-0 items-center gap-0 pr-3 text-base tracking-tight">
			<span class="flex-shrink-0 font-normal text-gray-500 dark:text-gray-400">{{ issue.name }}:</span>
			<input
				v-if="editingSubject"
				ref="subjectInput"
				v-model="subject"
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
				class="ml-1.5 min-w-0 flex-1 truncate rounded-sm text-left font-bold text-gray-900 hover:bg-gray-50 dark:text-gray-100 dark:hover:bg-gray-800/60"
				@click="startEditSubject"
			>
				{{ subject.trim() || "Untitled" }}
			</button>
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
					<Button
						v-if="status === 'Closed'"
						class="mt-2"
						variant="ghost"
						size="sm"
						:disabled="savingStatus"
						@click="changeStatus('Open')"
					>
						Reopen
					</Button>
				</section>

				<section class="space-y-3">
					<FormControl
						v-model="priority"
						label="Priority"
						type="select"
						size="sm"
						:options="priorityOptions"
					/>
					<FormControl
						v-model="issueType"
						label="Issue Type"
						type="select"
						size="sm"
						:options="issueTypeOptions"
					/>
					<FormControl
						v-model="project"
						label="Project"
						type="select"
						size="sm"
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
						method-name="set_assignees"
						@updated="onAssigneesUpdated"
					/>
				</section>
			</div>

			<div class="mt-auto flex-shrink-0 space-y-2 border-t border-outline-gray-2 p-4">
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
</template>

<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from "vue"
import { call, debounce, TextEditor, toast, Badge } from "frappe-ui"
import AssigneePicker from "@spa/components/AssigneePicker.vue"
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

const emit = defineEmits(["close", "updated"])

const API = computed(() => props.apiPrefix || spaConfig.api)
const propertiesHostReady = ref(false)
const chromeHostReady = ref(false)
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
const subject = ref(props.issue.subject || "")
const description = ref(props.issue.description || "")
const priority = ref(props.issue.priority || "")
const issueType = ref(props.issue.issue_type || "")
const project = ref(props.issue.project || "")
const assignees = ref([...(props.issue.assignees || [])])
const savingStatus = ref(false)
const savingFields = ref(false)
const fieldError = ref("")
const syncing = ref(false)
const editingSubject = ref(false)
const subjectInput = ref(null)
const subjectBeforeEdit = ref("")

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
		subject.value = subjectBeforeEdit.value || props.issue.subject || ""
	}
}

function cancelEditSubject() {
	subject.value = subjectBeforeEdit.value
	editingSubject.value = false
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
		syncing.value = true
		status.value = issue.status
		subject.value = issue.subject || ""
		description.value = issue.description || ""
		priority.value = issue.priority || ""
		issueType.value = issue.issue_type || ""
		project.value = issue.project || ""
		assignees.value = [...(issue.assignees || [])]
		fieldError.value = ""
		editingSubject.value = false
		nextTick(() => {
			syncing.value = false
		})
		syncPropertiesHost()
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
	const issue = props.issue
	return (
		subject.value.trim() !== (issue.subject || "").trim() ||
		normalizedDescription() !== (issue.description || "") ||
		(priority.value || "") !== (issue.priority || "") ||
		(issueType.value || "") !== (issue.issue_type || "") ||
		(project.value || "") !== (issue.project || "")
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
		const updated = await call(`${API.value}.update_issue`, {
			name: props.issue.name,
			subject: subject.value.trim(),
			description: normalizedDescription(),
			priority: priority.value || "",
			issue_type: issueType.value || "",
			project: project.value || "",
		})
		emit("updated", updated)
	} catch (e) {
		fieldError.value = e?.messages?.[0] || e?.message || "Could not save issue"
		toast.error(fieldError.value)
	} finally {
		savingFields.value = false
	}
}

const scheduleSave = debounce(() => {
	saveFields()
}, 500)

watch([subject, description, priority, issueType, project], () => {
	if (syncing.value) return
	scheduleSave()
})

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
</script>
