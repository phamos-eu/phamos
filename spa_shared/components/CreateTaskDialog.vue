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
					v-model="subject"
					label="Subject"
					type="text"
					required
					size="sm"
					placeholder="e.g. Prepare onboarding checklist"
				/>

				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Description</label>
					<TextEditor
						v-if="modelValue"
						:content="description"
						:fixed-menu="editorMenu"
						placeholder="What needs to be done?"
					editor-class="prose-sm dark:prose-invert min-h-[140px] max-h-[280px] overflow-y-auto px-3 py-2 border border-outline-gray-2 rounded-lg bg-surface-white"
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
				<ErrorMessage :message="error" />
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call, DatePicker, TextEditor } from "frappe-ui"
import { formatDate } from "@spa/utils/datetime.js"
import spaConfig from "@/config"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	options: {
		type: Object,
		default: () => ({
			priorities: [],
			projects: [],
		}),
	},
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

const subject = ref("")
const description = ref("")
const priority = ref("")
const project = ref("")
const expStartDate = ref("")
const expEndDate = ref("")
const saving = ref(false)
const error = ref("")

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
	() => props.modelValue,
	(open) => {
		if (!open) return
		subject.value = ""
		description.value = ""
		expStartDate.value = ""
		expEndDate.value = ""
		error.value = ""
		project.value =
			props.options[spaConfig.projectField] || props.options.projects?.[0]?.name || ""
		const priorities = props.options.priorities || []
		priority.value = priorities.includes("Medium") ? "Medium" : priorities[0] || ""
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
	error.value = ""
	if (!subject.value.trim()) {
		error.value = "Subject is required"
		return
	}
	saving.value = true
	try {
		const task = await call(`${API}.create_task`, {
			subject: subject.value.trim(),
			description: isEmptyHtml(description.value) ? "" : description.value,
			priority: priority.value || null,
			project: project.value || null,
			exp_start_date: expStartDate.value || null,
			exp_end_date: expEndDate.value || null,
		})
		emit("created", task)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not create task"
	} finally {
		saving.value = false
	}
}
</script>
