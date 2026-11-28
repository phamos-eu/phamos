<template>
	<Dialog
		:options="{
			title: 'New ToDo',
			size: '2xl',
			actions: [
				{ label: 'Cancel', variant: 'subtle', onClick: () => emit('update:modelValue', false) },
				{ label: saving ? 'Creating…' : 'Create', variant: 'solid', loading: saving, onClick: submit },
			],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-4">
				<div class="w-full">
					<label class="mb-1.5 block text-xs text-ink-gray-5">What needs doing? *</label>
					<TextEditor
						v-if="modelValue"
						:content="description"
						:fixed-menu="editorMenu"
						placeholder="e.g. Send the quotation to ACME"
						editor-class="prose-sm dark:prose-invert max-w-none w-full min-h-[100px] max-h-[240px] overflow-y-auto px-3 py-2 border border-t-0 border-gray-300 rounded-b-lg bg-white dark:border-gray-600 dark:bg-gray-800"
						@change="(html) => (description = html)"
					/>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<FormControl v-model="date" label="Due date" type="date" size="sm" :min="today" />
					<FormControl
						v-model="priority"
						label="Priority"
						type="select"
						size="sm"
						:options="TODO_PRIORITIES"
					/>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<FormControl
						v-model="referenceType"
						label="Reference (optional)"
						type="select"
						size="sm"
						:options="referenceTypeOptions"
					/>
					<div v-if="referenceType">
						<label class="mb-1.5 block text-xs text-ink-gray-5">{{ referenceType }}</label>
						<FrappeLink
							:key="referenceType"
							v-model="referenceName"
							:doctype="referenceType"
							:placeholder="`Select ${referenceType}`"
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
import { call, TextEditor } from "frappe-ui"
import FrappeLink from "@spa/components/FrappeLink.vue"
import { todayIsoInUserTz } from "@spa/utils/datetime.js"
import { isEmptyHtml } from "@spa/utils/autosaveCore.js"
import { TODO_PRIORITIES } from "@spa/utils/todoSort.js"
import spaConfig from "@/config"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
})

const emit = defineEmits(["update:modelValue", "created"])

const API = spaConfig.api
const editorMenu = [["Bold", "Italic"], ["Bullet List", "Numbered List"]]

const description = ref("")
const date = ref("")
const priority = ref("Medium")
const referenceType = ref("")
const referenceName = ref("")
const referenceTypes = ref([])
const saving = ref(false)
const error = ref("")
const today = computed(() => todayIsoInUserTz())

const referenceTypeOptions = computed(() => [
	{ label: "None", value: "" },
	...referenceTypes.value.map((doctype) => ({ label: doctype, value: doctype })),
])

watch(referenceType, () => {
	referenceName.value = ""
})

watch(
	() => props.modelValue,
	async (open) => {
		if (!open) return
		description.value = ""
		date.value = todayIsoInUserTz()
		priority.value = "Medium"
		referenceType.value = ""
		referenceName.value = ""
		error.value = ""
		if (!referenceTypes.value.length) {
			try {
				referenceTypes.value = await call(`${API}.get_todo_reference_types`)
			} catch (e) {
				referenceTypes.value = []
			}
		}
	}
)

async function submit() {
	if (isEmptyHtml(description.value)) {
		error.value = "Please describe what needs doing."
		return
	}
	if (referenceType.value && !referenceName.value) {
		error.value = `Select a ${referenceType.value}, or set the reference to None.`
		return
	}
	saving.value = true
	error.value = ""
	try {
		const todo = await call(`${API}.create_todo`, {
			description: description.value,
			date: date.value || null,
			priority: priority.value,
			reference_type: referenceType.value || null,
			reference_name: referenceName.value || null,
		})
		emit("created", todo)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not create the ToDo"
	} finally {
		saving.value = false
	}
}
</script>
