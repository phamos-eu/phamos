<template>
	<Dialog
		:options="{
			title: entry ? 'Edit feedback' : 'Add feedback',
			size: '2xl',
			actions: [
				{ label: 'Cancel', variant: 'subtle', onClick: () => emit('update:modelValue', false) },
				{ label: saving ? 'Saving…' : 'Save', variant: 'solid', loading: saving, onClick: submit },
			],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-3">
				<div class="grid grid-cols-2 gap-3">
					<FormControl v-model="respondentName" label="Respondent" type="text" size="sm" />
					<FormControl
						v-model="audience"
						label="Audience"
						type="select"
						size="sm"
						:options="[
							{ label: 'Internal', value: 'Internal' },
							{ label: 'External', value: 'External' },
						]"
					/>
				</div>

				<!-- The people already on the demo are who usually has an opinion about it. -->
				<div v-if="availableAttendees.length" class="flex flex-wrap items-center gap-1.5">
					<span class="text-xs text-ink-gray-5">From the attendees:</span>
					<button
						v-for="person in availableAttendees"
						:key="person.full_name"
						type="button"
						class="rounded-full border border-dashed border-outline-gray-3 px-2 py-0.5 text-xs text-ink-gray-8 hover:border-outline-gray-4 hover:bg-surface-gray-2"
						@click="pickAttendee(person)"
					>
						+ {{ person.full_name }}
					</button>
				</div>

				<LeadModulePicker v-model="modules" />

				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Notes</label>
					<TextEditor
						v-if="modelValue"
						:content="notes"
						:fixed-menu="editorMenu"
						placeholder="What did they make of the demo?"
						editor-class="prose-sm dark:prose-invert max-w-none w-full min-h-[140px] max-h-[40vh] overflow-y-auto px-3 py-2 border border-t-0 border-outline-gray-2 rounded-b-lg bg-surface-white"
						@change="(html) => (notes = html)"
					/>
				</div>

				<ErrorMessage :message="error" />
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call, TextEditor } from "frappe-ui"
import LeadModulePicker from "./LeadModulePicker.vue"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	demo: { type: Object, required: true },
	/** The feedback being edited, or null to create one. */
	entry: { type: Object, default: null },
})

const emit = defineEmits(["update:modelValue", "saved"])

const editorMenu = ["Paragraph", "Bold", "Italic", "Link", "Separator", "Bullet List", "Numbered List"]

const respondentName = ref("")
const audience = ref("Internal")
const contact = ref(null)
const user = ref(null)
const modules = ref([])
const notes = ref("")
const saving = ref(false)
const error = ref("")

/** Attendees who haven't given their view yet — only useful while creating. */
const availableAttendees = computed(() => {
	if (props.entry) return []
	return (props.demo.attendees || []).filter((a) => a.full_name)
})

function pickAttendee(person) {
	respondentName.value = person.full_name
	contact.value = person.contact || null
	user.value = person.user || null
	audience.value = person.audience === "Internal" ? "Internal" : "External"
}

async function submit() {
	error.value = ""
	if (!respondentName.value.trim()) {
		error.value = "A respondent is required."
		return
	}

	saving.value = true
	try {
		await call("phamos.api.sales_demos.save_demo_feedback", {
			demo: props.demo.name,
			name: props.entry?.name || null,
			respondent_name: respondentName.value.trim(),
			audience: audience.value,
			contact: contact.value,
			user: user.value,
			notes: notes.value,
			modules: JSON.stringify(modules.value.map((row) => ({ module: row.module }))),
		})
		emit("saved")
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not save the feedback"
	} finally {
		saving.value = false
	}
}

watch(
	() => props.modelValue,
	(open) => {
		if (!open) return
		error.value = ""
		const entry = props.entry
		respondentName.value = entry?.respondent_name || ""
		audience.value = entry?.audience || "Internal"
		contact.value = entry?.contact || null
		user.value = entry?.user || null
		modules.value = entry?.modules ? [...entry.modules] : []
		notes.value = entry?.notes || ""
	}
)
</script>
