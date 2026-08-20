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
				<div>
					<label class="mb-1 block text-xs font-medium text-gray-600">Subject *</label>
					<input
						v-model="subject"
						type="text"
						class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
						placeholder="e.g. Onboarding step X is broken"
					/>
				</div>

				<div>
					<label class="mb-1 block text-xs font-medium text-gray-600">Description</label>
					<p class="mb-1 text-[11px] text-gray-500">
						Paste or insert screenshots via the image button.
					</p>
					<TextEditor
						v-if="modelValue"
						:content="description"
						:fixed-menu="editorMenu"
						placeholder="What needs to be fixed or followed up?"
						editor-class="prose-sm min-h-[140px] max-h-[280px] overflow-y-auto px-3 py-2 border border-t-0 border-gray-300 rounded-b-lg bg-white"
						@change="(html) => (description = html)"
					/>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label class="mb-1 block text-xs font-medium text-gray-600">Priority</label>
						<select v-model="priority" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm">
							<option value="">—</option>
							<option v-for="p in options.priorities" :key="p" :value="p">{{ p }}</option>
						</select>
					</div>
					<div>
						<label class="mb-1 block text-xs font-medium text-gray-600">Issue Type</label>
						<select v-model="issueType" class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm">
							<option value="">—</option>
							<option v-for="t in options.issue_types" :key="t" :value="t">{{ t }}</option>
						</select>
					</div>
					<div>
						<label class="mb-1 block text-xs font-medium text-gray-600">Department</label>
						<select
							v-model="department"
							class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
						>
							<option value="">—</option>
							<option v-for="d in options.departments || []" :key="d" :value="d">{{ d }}</option>
						</select>
					</div>
					<div>
						<label class="mb-1 block text-xs font-medium text-gray-600">Project</label>
						<select
							v-model="project"
							class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
						>
							<option value="">—</option>
							<option
								v-for="p in options.projects || []"
								:key="p.name"
								:value="p.name"
							>
								{{ p.project_name || p.name }}
							</option>
						</select>
					</div>
				</div>

				<div>
					<label class="mb-1 block text-xs font-medium text-gray-600">Assign to</label>
					<div class="max-h-40 overflow-y-auto rounded-md border border-gray-200 p-1">
						<label
							v-for="u in options.users"
							:key="u.name"
							class="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-gray-50"
						>
							<input
								type="checkbox"
								:checked="assignTo.includes(u.name)"
								@change="toggleUser(u.name)"
							/>
							<span>{{ u.full_name }}</span>
						</label>
					</div>
				</div>
				<p v-if="error" class="text-sm text-red-600">{{ error }}</p>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { ref, watch } from "vue"
import { call, TextEditor } from "frappe-ui"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	options: {
		type: Object,
		default: () => ({
			priorities: [],
			issue_types: [],
			users: [],
			departments: [],
			projects: [],
		}),
	},
})

const emit = defineEmits(["update:modelValue", "created"])

const API = "phamos.api.i_own_my_work"
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

watch(
	() => props.modelValue,
	(open) => {
		if (!open) return
		subject.value = ""
		description.value = ""
		issueType.value = ""
		department.value = ""
		project.value = ""
		assignTo.value = []
		error.value = ""
		const priorities = props.options.priorities || []
		priority.value = priorities.includes("Medium") ? "Medium" : priorities[0] || ""
	}
)

function toggleUser(name) {
	if (assignTo.value.includes(name)) {
		assignTo.value = assignTo.value.filter((u) => u !== name)
	} else {
		assignTo.value = [...assignTo.value, name]
	}
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
