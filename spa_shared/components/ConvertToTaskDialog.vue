<template>
	<Dialog
		:options="{
			title: 'Convert to Task',
			size: '4xl',
			actions: [
				{
					label: 'Cancel',
					variant: 'subtle',
					onClick: () => emit('update:modelValue', false),
				},
				{
					label: saving ? 'Converting…' : 'Convert',
					variant: 'solid',
					loading: saving,
					onClick: submit,
				},
			],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-4">
				<p class="text-sm text-ink-gray-6">
					Creates a Task linked to
					<span class="font-medium text-ink-gray-8">{{ issue?.name }}</span>,
					moves checklists, and closes the Issue.
				</p>

				<FormControl
					v-model="subject"
					label="Subject"
					type="text"
					required
					size="sm"
					placeholder="Task subject"
				/>

				<div class="w-full">
					<label class="mb-1.5 block text-xs text-ink-gray-5">Description</label>
					<TextEditor
						v-if="modelValue"
						:content="description"
						:fixed-menu="editorMenu"
						placeholder="What needs to be done?"
						editor-class="prose-sm dark:prose-invert max-w-none w-full min-h-[140px] max-h-[280px] overflow-y-auto px-3 py-2 border border-t-0 border-outline-gray-2 rounded-b-lg bg-surface-white"
						@change="(html) => (description = html)"
					/>
				</div>

				<div class="grid grid-cols-2 gap-3">
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
				</div>

				<SchedulePreview
					:start-date="expStartDate"
					:end-date="expEndDate"
					:subject="subject"
					:api-prefix="API"
					:linked-task-ids="linkedTaskIds"
					@select-task="onToggleDependency"
				/>

				<p
					v-if="dateWarning"
					class="text-xs text-ink-amber-3"
				>
					{{ dateWarning }}
				</p>

				<AssigneePicker
					v-model="assignees"
					:assignee-details="assigneeDetails"
					:shortlist-users="options.shortlist_users || []"
				/>
				<ErrorMessage :message="error" />
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call, DatePicker, TextEditor } from "frappe-ui"
import AssigneePicker from "@spa/components/AssigneePicker.vue"
import SchedulePreview from "@spa/components/SchedulePreview.vue"
import { formatDate } from "@spa/utils/datetime.js"
import spaConfig from "@/config"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	issue: { type: Object, default: null },
	options: {
		type: Object,
		default: () => ({
			priorities: [],
			projects: [],
			shortlist_users: [],
		}),
	},
	apiPrefix: {
		type: String,
		default: "",
	},
})

const emit = defineEmits(["update:modelValue", "converted"])

const API = computed(() => props.apiPrefix || spaConfig.api)
const TASK_PRIORITIES = ["Low", "Medium", "High", "Urgent"]
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

const subject = ref("")
const description = ref("")
const priority = ref("")
const project = ref("")
const expStartDate = ref("")
const expEndDate = ref("")
const assignees = ref([])
const dependencies = ref([])
const saving = ref(false)
const error = ref("")

const assigneeDetails = computed(() => {
	const issue = props.issue || {}
	const names = issue.assignees || []
	const labels = issue.assignee_names || []
	const images = issue.assignee_images || []
	return names.map((name, i) => ({
		name,
		full_name: labels[i] || name,
		user_image: images[i] || "",
	}))
})

const linkedTaskIds = computed(() => dependencies.value.map((d) => d.name))

const priorityOptions = computed(() => [
	{ label: "—", value: "" },
	...TASK_PRIORITIES.map((p) => ({ label: p, value: p })),
])

const projectOptions = computed(() => [
	{ label: "—", value: "" },
	...(props.options.projects || []).map((p) => ({
		label: p.project_name || p.name,
		value: p.name,
	})),
])

const dateWarning = computed(() => {
	const start = String(expStartDate.value || "").slice(0, 10)
	if (!start || !dependencies.value.length) return ""
	const conflicts = dependencies.value.filter((d) => {
		const end = String(d.exp_end_date || "").slice(0, 10)
		return end && start < end
	})
	if (!conflicts.length) return ""
	if (conflicts.length === 1) {
		const d = conflicts[0]
		return `Start is before predecessor end (${d.name} ends ${formatDate(d.exp_end_date)}).`
	}
	return `Start is before ${conflicts.length} predecessor end dates.`
})

function mapIssuePriority(value) {
	const raw = String(value || "").trim()
	if (!raw) return TASK_PRIORITIES.includes("Medium") ? "Medium" : TASK_PRIORITIES[0] || ""
	const exact = TASK_PRIORITIES.find((p) => p === raw || p.toLowerCase() === raw.toLowerCase())
	return exact || (TASK_PRIORITIES.includes("Medium") ? "Medium" : TASK_PRIORITIES[0] || "")
}

watch(
	() => props.modelValue,
	(open) => {
		if (!open) return
		const issue = props.issue || {}
		subject.value = issue.subject || ""
		description.value = issue.description || ""
		project.value = issue.project || props.options[spaConfig.projectField] || ""
		priority.value = mapIssuePriority(issue.priority)
		assignees.value = [...(issue.assignees || [])]
		expStartDate.value = ""
		expEndDate.value = ""
		dependencies.value = []
		error.value = ""
	}
)

function onToggleDependency(task) {
	if (!task?.name) return
	if (dependencies.value.some((d) => d.name === task.name)) {
		dependencies.value = dependencies.value.filter((d) => d.name !== task.name)
		return
	}
	dependencies.value = [
		...dependencies.value,
		{
			name: task.name,
			subject: task.subject || task.name,
			exp_start_date: task.exp_start_date || "",
			exp_end_date: task.exp_end_date || task.exp_start_date || "",
		},
	]
}

function isEmptyHtml(html) {
	if (!html) return true
	const text = String(html)
		.replace(/<img[^>]*>/gi, "img")
		.replace(/<[^>]+>/g, "")
		.replace(/&nbsp;/g, " ")
		.trim()
	return !text
}

async function submit() {
	if (saving.value) return
	error.value = ""
	if (!props.issue?.name) {
		error.value = "Issue is required"
		return
	}
	if (!subject.value.trim()) {
		error.value = "Subject is required"
		return
	}
	if (!expStartDate.value || !expEndDate.value) {
		error.value = "Expected start and end dates are required"
		return
	}
	if (String(expEndDate.value) < String(expStartDate.value)) {
		error.value = "Expected end date cannot be before start date"
		return
	}
	if (!(assignees.value || []).length) {
		error.value = "At least one assignee is required"
		return
	}

	saving.value = true
	try {
		const result = await call(`${API.value}.create_task_from_issue`, {
			issue_name: props.issue.name,
			subject: subject.value.trim(),
			description: isEmptyHtml(description.value) ? "" : description.value,
			priority: priority.value || null,
			project: project.value || null,
			exp_start_date: expStartDate.value,
			exp_end_date: expEndDate.value,
			assignees: assignees.value,
			depends_on: dependencies.value.map((d) => d.name),
		})
		emit("converted", result)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not convert to task"
	} finally {
		saving.value = false
	}
}
</script>
