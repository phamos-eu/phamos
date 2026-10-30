<template>
	<Dialog
		:options="{
			title: 'New Task',
			size: '3xl',
			actions: [
				{
					label: 'Cancel',
					variant: 'subtle',
					onClick: () => emit('update:modelValue', false),
				},
				{
					label: saving ? 'Creating…' : 'Create',
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
				<FormControl
					v-model="form.subject"
					label="Subject"
					type="text"
					required
					size="sm"
					placeholder="e.g. Prepare onboarding checklist"
				/>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">Expected start *</label>
						<DatePicker
							v-model="startDate"
							placeholder="Start date"
							class="w-full"
							:formatter="formatDate"
						/>
					</div>
					<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">Expected end *</label>
						<DatePicker
							v-model="form.exp_end_date"
							placeholder="End date"
							class="w-full"
							:formatter="formatDate"
						/>
					</div>
					<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">Task Owner *</label>
						<FrappeLink
							v-model="form.custom_task_owner"
							doctype="User"
							:filters="{ enabled: 1, user_type: 'System User' }"
							placeholder="Who is responsible"
						/>
					</div>
					<FormControl
						v-model="form.expected_time"
						label="Estimated time (hours) *"
						type="number"
						size="sm"
						min="0"
						step="0.25"
					/>
					<FormControl
						v-model="form.priority"
						label="Priority *"
						type="select"
						size="sm"
						:options="priorityOptions"
					/>
					<FormControl
						v-model="form.project"
						label="Project"
						type="select"
						size="sm"
						:options="projectOptions"
					/>
					<FormControl
						v-model="form.task_type"
						label="Task type"
						type="select"
						size="sm"
						:options="taskTypeOptions"
					/>
				</div>

				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Description</label>
					<TextEditor
						v-if="modelValue"
						:content="form.description"
						:fixed-menu="editorMenu"
						placeholder="What needs to be done?"
						editor-class="prose-sm dark:prose-invert min-h-[120px] max-h-[240px] overflow-y-auto px-3 py-2 border border-outline-gray-2 rounded-lg bg-surface-white"
						@change="(html) => (form.description = html)"
					/>
				</div>
				<ErrorMessage :message="error" />
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call, DatePicker, TextEditor } from "frappe-ui"
import FrappeLink from "@spa/components/FrappeLink.vue"
import { formatDate, todayIsoInUserTz } from "@spa/utils/datetime.js"
import { newTaskDefaults, newTaskErrors, withStartDate } from "@spa/utils/newTaskForm.js"
import { session } from "@spa/session.js"
import spaConfig from "@/config"

// The one "New Task" dialog of all cockpits (#1752): the Gantt's "New task…" and the
// personal cockpit's create menu. Converting an Issue keeps ConvertToTaskDialog.
const props = defineProps({
	modelValue: { type: Boolean, default: false },
	options: {
		type: Object,
		default: () => ({ task_priorities: [], task_types: [], projects: [] }),
	},
	// What was typed into "New task…" before the dialog opened.
	initialSubject: { type: String, default: "" },
})

const emit = defineEmits(["update:modelValue", "created"])

const API = spaConfig.api
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

const form = ref(newTaskDefaults({ today: todayIsoInUserTz() }))
const saving = ref(false)
const error = ref("")

const startDate = computed({
	get: () => form.value.exp_start_date,
	set: (value) => (form.value = withStartDate(form.value, value)),
})

const priorityOptions = computed(() =>
	(props.options.task_priorities || []).map((p) => ({ label: p, value: p }))
)

const projectOptions = computed(() => [
	{ label: "—", value: "" },
	...(props.options.projects || []).map((p) => ({
		label: p.project_name || p.name,
		value: p.name,
	})),
])

const taskTypeOptions = computed(() => [
	{ label: "—", value: "" },
	...(props.options.task_types || []).map((t) => ({ label: t, value: t })),
])

watch(
	() => props.modelValue,
	(open) => {
		if (!open) return
		error.value = ""
		form.value = newTaskDefaults({
			subject: props.initialSubject,
			today: todayIsoInUserTz(),
			user: session.user,
			options: props.options,
			projectField: spaConfig.projectField,
		})
	}
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

async function submit() {
	if (saving.value) return
	const errors = newTaskErrors(form.value)
	error.value = errors.join(". ")
	if (errors.length) return

	const f = form.value
	saving.value = true
	try {
		const task = await call(`${API}.create_task`, {
			subject: f.subject.trim(),
			exp_start_date: f.exp_start_date,
			exp_end_date: f.exp_end_date,
			custom_task_owner: f.custom_task_owner,
			expected_time: Number(f.expected_time),
			priority: f.priority,
			project: f.project || null,
			task_type: f.task_type || null,
			description: isEmptyHtml(f.description) ? "" : f.description,
		})
		emit("created", task)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not create task"
	} finally {
		saving.value = false
	}
}
</script>
