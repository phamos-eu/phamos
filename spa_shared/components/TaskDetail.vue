<template>
	<div class="flex h-full min-h-0 flex-col">
		<header
			class="flex flex-shrink-0 items-start justify-between gap-4 border-b border-gray-200 px-5 py-4 dark:border-gray-800"
		>
			<div class="min-w-0 flex-1">
				<div class="mb-1 text-xs font-semibold text-gray-500 dark:text-gray-400">{{ task.name }}</div>
				<div class="text-xs text-gray-500 dark:text-gray-400">
					{{ task.owner_name || task.owner || "—" }}
					<span v-if="task.department"> · {{ task.department }}</span>
				</div>
			</div>
			<div class="flex items-center gap-2">
				<Button variant="subtle" :link="task.desk_url">Open in Desk</Button>
				<Button variant="ghost" @click="emit('close')">Close</Button>
			</div>
		</header>

		<div class="flex-1 space-y-5 overflow-y-auto px-5 py-4 text-gray-900 dark:text-gray-100">
			<section>
				<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
					Status
				</div>
				<div class="flex flex-wrap gap-2">
					<Button
						v-for="s in statuses"
						:key="s"
						size="sm"
						:variant="status === s ? 'solid' : 'outline'"
						:disabled="savingStatus"
						@click="changeStatus(s)"
					>
						{{ s }}
					</Button>
				</div>
			</section>

			<section class="space-y-4">
				<FormControl v-model="subject" label="Subject" type="text" required size="sm" />
				<div class="w-full">
					<label class="mb-1.5 block text-xs text-ink-gray-5">Description</label>
					<TextEditor
						:content="description"
						:fixed-menu="editorMenu"
						placeholder="Task details…"
						editor-class="prose-sm dark:prose-invert max-w-none w-full min-h-[160px] px-3 py-2 border border-t-0 border-gray-300 rounded-b-lg bg-white dark:border-gray-600 dark:bg-gray-800"
						@change="(html) => (description = html)"
					/>
				</div>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
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
						<DatePicker v-model="expStartDate" placeholder="Start date" class="w-full" />
					</div>
					<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">Expected end</label>
						<DatePicker v-model="expEndDate" placeholder="End date" class="w-full" />
					</div>
					<FormControl
						v-model="progress"
						label="Progress %"
						type="number"
						size="sm"
						:min="0"
						:max="100"
					/>
				</div>
				<div class="flex items-center gap-2">
					<Button variant="solid" :loading="savingFields" @click="saveFields">Save changes</Button>
					<ErrorMessage :message="fieldError" />
				</div>
			</section>

			<LinkedChecklistsSection
				document="Task"
				:reference-record="task.name"
				:reference-title="subject || task.subject"
			/>

			<section class="mb-5">
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
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call, DatePicker, TextEditor, toast } from "frappe-ui"
import AssigneePicker from "@spa/components/AssigneePicker.vue"
import LinkedChecklistsSection from "@spa/components/LinkedChecklistsSection.vue"
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

const status = ref(props.task.status)
const subject = ref(props.task.subject || "")
const description = ref(props.task.description || "")
const priority = ref(props.task.priority || "")
const project = ref(props.task.project || "")
const expStartDate = ref(props.task.exp_start_date || "")
const expEndDate = ref(props.task.exp_end_date || "")
const progress = ref(String(props.task.progress ?? 0))
const assignees = ref([...(props.task.assignees || [])])
const savingStatus = ref(false)
const savingFields = ref(false)
const fieldError = ref("")

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

watch(
	() => props.task,
	(task) => {
		status.value = task.status
		subject.value = task.subject || ""
		description.value = task.description || ""
		priority.value = task.priority || ""
		project.value = task.project || ""
		expStartDate.value = task.exp_start_date || ""
		expEndDate.value = task.exp_end_date || ""
		progress.value = String(task.progress ?? 0)
		assignees.value = [...(task.assignees || [])]
		fieldError.value = ""
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

async function saveFields() {
	fieldError.value = ""
	if (!subject.value.trim()) {
		fieldError.value = "Subject is required"
		return
	}
	savingFields.value = true
	try {
		const updated = await call(`${API.value}.update_task`, {
			name: props.task.name,
			subject: subject.value.trim(),
			description: isEmptyHtml(description.value) ? "" : description.value,
			priority: priority.value || "",
			project: project.value || "",
			exp_start_date: expStartDate.value || "",
			exp_end_date: expEndDate.value || "",
			progress: progress.value === "" ? 0 : Number(progress.value),
		})
		emit("updated", updated)
		toast.success("Task updated")
	} catch (e) {
		fieldError.value = e?.messages?.[0] || e?.message || "Could not save task"
	} finally {
		savingFields.value = false
	}
}

function onAssigneesUpdated(updated) {
	assignees.value = [...(updated.assignees || [])]
	emit("updated", updated)
}
</script>
