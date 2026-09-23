<template>
	<Dialog
		:options="{
			title: 'New Issue',
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
					placeholder="e.g. Policy update for remote work"
				/>

				<div class="w-full">
					<label class="mb-1.5 block text-xs text-ink-gray-5">Description</label>
					<TextEditor
						v-if="modelValue"
						:content="description"
						:fixed-menu="editorMenu"
						placeholder="What needs to be discussed or resolved?"
						editor-class="prose-sm dark:prose-invert max-w-none w-full min-h-[140px] max-h-[280px] overflow-y-auto px-3 py-2 border border-t-0 border-gray-300 rounded-b-lg bg-white dark:border-gray-600 dark:bg-gray-800"
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
						v-model="issueType"
						label="Issue Type"
						type="select"
						size="sm"
						:options="issueTypeOptions"
					/>
					<FormControl
						v-model="department"
						label="Department"
						type="select"
						size="sm"
						:options="departmentOptions"
					/>
					<FormControl
						v-model="project"
						label="Project"
						type="select"
						size="sm"
						:options="projectOptions"
					/>
				</div>

				<AssigneePicker
					v-model="assignTo"
					:shortlist-users="options.shortlist_users || []"
				/>
				<ErrorMessage :message="error" />
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call, TextEditor } from "frappe-ui"
import AssigneePicker from "@spa/components/AssigneePicker.vue"
import spaConfig from "@/config"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	options: {
		type: Object,
		default: () => ({
			priorities: [],
			issue_types: [],
			shortlist_users: [],
			departments: [],
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
	"Separator",
	"Image",
]

const subject = ref("")
const description = ref("")
const priority = ref("")
const issueType = ref("")
const department = ref("")
const project = ref("")
const assignTo = ref([])
const saving = ref(false)
const error = ref("")

const priorityOptions = computed(() => [
	{ label: "—", value: "" },
	...(props.options.priorities || []).map((p) => ({ label: p, value: p })),
])

const issueTypeOptions = computed(() => [
	{ label: "—", value: "" },
	...(props.options.issue_types || []).map((t) => ({ label: t, value: t })),
])

const departmentOptions = computed(() => [
	{ label: "—", value: "" },
	...(props.options.departments || []).map((d) => ({ label: d, value: d })),
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
		issueType.value = ""
		assignTo.value = []
		error.value = ""
		department.value =
			props.options[spaConfig.departmentField] || props.options.departments?.[0] || ""
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
	error.value = ""
	if (!subject.value.trim()) {
		error.value = "Subject is required"
		return
	}
	saving.value = true
	try {
		const issue = await call(`${API}.create_issue`, {
			subject: subject.value.trim(),
			description: isEmptyHtml(description.value) ? "" : description.value,
			priority: priority.value || null,
			issue_type: issueType.value || null,
			department: department.value || null,
			project: project.value || null,
			assign_to: assignTo.value,
		})
		emit("created", issue)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not create issue"
	} finally {
		saving.value = false
	}
}
</script>
