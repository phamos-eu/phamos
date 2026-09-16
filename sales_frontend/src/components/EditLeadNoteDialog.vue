<template>
	<Dialog
		:options="{
			title: 'Edit note',
			size: 'lg',
			actions: [
				{ label: 'Cancel', variant: 'subtle', onClick: () => emit('update:modelValue', false) },
				{
					label: saving ? 'Saving…' : 'Save',
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
			<div class="space-y-3">
				<FormControl v-model="content" type="textarea" rows="6" size="sm" label="Note" />
				<p v-if="note?.added_by_name" class="text-xs text-ink-gray-5">
					Added by {{ note.added_by_name }}
				</p>
				<ErrorMessage :message="error" />
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { ref, watch } from "vue"
import { call } from "frappe-ui"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	lead: { type: Object, required: true },
	/** { name, note, added_by_name } */
	note: { type: Object, default: null },
})

const emit = defineEmits(["update:modelValue", "saved"])

const content = ref("")
const saving = ref(false)
const error = ref("")

watch(
	() => props.modelValue,
	(open) => {
		if (!open) return
		error.value = ""
		// The stored value, not the stripped preview — editing shouldn't
		// silently discard formatting on notes written in Desk.
		content.value = props.note?.note || ""
	}
)

async function submit() {
	error.value = ""
	if (!content.value.trim()) {
		error.value = "A note can't be empty."
		return
	}

	saving.value = true
	try {
		const notes = await call("phamos.api.sales_leads.update_lead_note", {
			lead: props.lead.name,
			note_name: props.note.name,
			content: content.value.trim(),
		})
		emit("saved", notes)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not save the note"
	} finally {
		saving.value = false
	}
}
</script>
