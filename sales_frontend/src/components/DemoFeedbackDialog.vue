<template>
	<Dialog
		:options="{
			title: entry ? 'Edit feedback' : 'Add feedback',
			size: 'xl',
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
						:options="audienceOptions"
					/>
				</div>

				<!-- Whoever was in the room, so the name doesn't have to be retyped. -->
				<div v-if="availableAttendees.length" class="flex flex-wrap items-center gap-1.5">
					<span class="text-xs text-ink-gray-5">From the attendees:</span>
					<button
						v-for="person in availableAttendees"
						:key="person.name || person.email"
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
						placeholder="What did they say?"
						editor-class="prose-sm dark:prose-invert max-w-none w-full min-h-[140px] max-h-[40vh] overflow-y-auto px-3 py-2 border border-t-0 border-outline-gray-2 rounded-b-lg bg-surface-white"
						@change="(html) => (notes = html)"
					/>
				</div>

				<p class="text-xs text-ink-gray-5">
					Internal feedback stays with us; external is what the customer told us.
				</p>
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
	/** The entry being edited, or null to add a new one. */
	entry: { type: Object, default: null },
})

const emit = defineEmits(["update:modelValue", "saved"])

const editorMenu = ["Paragraph", "Bold", "Italic", "Separator", "Bullet List", "Numbered List"]

const audienceOptions = [
	{ label: "Internal", value: "Internal" },
	{ label: "External", value: "External" },
]

const respondentName = ref("")
const audience = ref("Internal")
const contact = ref("")
const user = ref("")
const modules = ref([])
const notes = ref("")
const saving = ref(false)
const error = ref("")

const availableAttendees = computed(() =>
	(props.demo?.attendees || []).filter((person) => person.full_name)
)

function pickAttendee(person) {
	respondentName.value = person.full_name
	contact.value = person.contact || ""
	user.value = person.user || ""
	// An attendee marked as one of ours is giving internal feedback.
	audience.value = person.audience === "Internal" ? "Internal" : "External"
}

async function submit() {
	error.value = ""
	if (!respondentName.value.trim()) {
		error.value = "A respondent name is required."
		return
	}

	saving.value = true
	try {
		await call("phamos.api.sales_demos.save_demo_feedback", {
			demo: props.demo.name,
			name: props.entry?.name || null,
			respondent_name: respondentName.value.trim(),
			audience: audience.value,
			contact: contact.value || null,
			user: user.value || null,
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
		contact.value = entry?.contact || ""
		user.value = entry?.user || ""
		modules.value = entry?.modules ? entry.modules.map((row) => ({ ...row })) : []
		notes.value = entry?.notes || ""
	}
)
</script>
