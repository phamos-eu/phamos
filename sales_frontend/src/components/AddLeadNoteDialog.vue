<template>
	<Dialog
		:options="{
			title: `Note — ${lead.lead_name || lead.name}`,
			size: 'lg',
			actions: [
				{ label: 'Cancel', variant: 'subtle', onClick: () => emit('update:modelValue', false) },
				{ label: saving ? 'Saving…' : 'Save', variant: 'solid', loading: saving, onClick: submit },
			],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-4">
				<FormControl
					v-model="content"
					type="textarea"
					label="Note"
					size="sm"
					placeholder="What did you discuss?"
				/>
				<div class="w-full">
					<label class="mb-1.5 block text-xs text-ink-gray-5">Next Follow Up On</label>
					<input
						v-model="nextFollowUp"
						type="date"
						class="form-input block h-8 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8"
					/>
				</div>
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
})

const emit = defineEmits(["update:modelValue", "saved"])

const content = ref("")
// Date-only (YYYY-MM-DD), bound straight to an <input type="date">.
const nextFollowUp = ref("")
const saving = ref(false)
const error = ref("")

watch(
	() => props.modelValue,
	(open) => {
		if (!open) return
		content.value = ""
		error.value = ""
		nextFollowUp.value = props.lead.custom_next_followup || ""
	}
)

async function submit() {
	error.value = ""
	const note = content.value.trim()

	if (!note && !nextFollowUp.value) {
		error.value = "Enter a note or set a next follow-up date."
		return
	}

	saving.value = true
	try {
		const updated = await call("phamos.api.sales_leads.add_lead_note", {
			lead: props.lead.name,
			content: note,
			next_follow_up_on: nextFollowUp.value || null,
		})
		emit("saved", updated)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not save note"
	} finally {
		saving.value = false
	}
}
</script>
