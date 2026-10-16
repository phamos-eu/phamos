<template>
	<Dialog
		:options="{
			title: 'New expense category',
			size: 'lg',
			actions: [
				{ label: 'Cancel', variant: 'subtle', onClick: () => emit('update:modelValue', false) },
				{ label: saving ? 'Creating…' : 'Create', variant: 'solid', loading: saving, onClick: submit },
			],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<p class="mb-3 text-sm text-ink-gray-6">
				A category groups receipt lines of one kind of expense and carries the expense account. Keep the list short: create one only when no existing category fits.
			</p>
			<div class="space-y-3 text-sm">
				<label class="field">
					<span>Name *</span>
					<input v-model="form.name" class="input" placeholder="e.g. Internet-Anschluss" />
				</label>
				<label class="field">
					<span>Expense account *</span>
					<FrappeLink v-model="form.expense_account" doctype="Account" :filters="accountFilters" placeholder="e.g. 6810 Telefax und Internetkosten" />
				</label>
				<label class="field">
					<span>Keywords</span>
					<input v-model="form.keywords" class="input" placeholder="comma separated, e.g. dsl, glasfaser, internetanschluss" />
				</label>
			</div>
			<p v-if="error" class="mt-3 text-sm text-ink-red-4">{{ error }}</p>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, reactive, ref } from "vue"
import { call, Dialog } from "frappe-ui"
import FrappeLink from "@spa/components/FrappeLink.vue"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	company: { type: String, default: "" },
})
const emit = defineEmits(["update:modelValue", "created"])

const form = reactive({ name: "", expense_account: "", keywords: "" })
const saving = ref(false)
const error = ref("")
const accountFilters = computed(() => ({ root_type: "Expense", is_group: 0, ...(props.company ? { company: props.company } : {}) }))

async function submit() {
	error.value = ""
	if (!form.name.trim() || !form.expense_account) {
		error.value = "Name and expense account are required."
		return
	}
	saving.value = true
	try {
		const res = await call("phamos.api.accounting_receipts.create_expense_category", { ...form, company: props.company })
		emit("created", res.item_code)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not create the category"
	} finally {
		saving.value = false
	}
}
</script>

<style scoped>
.field {
	@apply flex flex-col gap-1;
}
.field > span {
	@apply text-xs text-ink-gray-5;
}
.input {
	@apply h-8 rounded-md border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-9;
}
</style>
