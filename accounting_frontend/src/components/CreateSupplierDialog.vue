<template>
	<Dialog
		:options="{
			title: 'Create supplier',
			size: 'xl',
			actions: [
				{ label: 'Cancel', variant: 'subtle', onClick: () => emit('update:modelValue', false) },
				{ label: saving ? 'Creating…' : 'Create and use', variant: 'solid', loading: saving, onClick: submit },
			],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<p class="mb-3 text-sm text-ink-gray-6">
				Prefilled with what the AI read on the receipt. Check it, then create the supplier; it is set on the receipt right away.
			</p>
			<div class="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2" @keydown.meta.enter="submit" @keydown.ctrl.enter="submit">
				<label class="field sm:col-span-2">
					<span>Supplier name *</span>
					<input v-model="form.supplier_name" class="input" autofocus />
				</label>
				<label class="field">
					<span>VAT ID</span>
					<input v-model="form.tax_id" class="input" />
				</label>
				<label class="field">
					<span>Tax category{{ taxCategoryRequired ? " *" : "" }}</span>
					<FrappeLink v-model="form.tax_category" doctype="Tax Category" />
				</label>
				<label class="field">
					<span>Supplier group</span>
					<FrappeLink v-model="form.supplier_group" doctype="Supplier Group" />
				</label>
				<label class="field">
					<span>Country</span>
					<FrappeLink v-model="form.country" doctype="Country" />
				</label>
				<label class="field sm:col-span-2">
					<span>Address</span>
					<input v-model="form.address_line1" class="input" placeholder="Street and number" />
				</label>
				<label class="field sm:col-span-2">
					<input v-model="form.address_line2" class="input" placeholder="Address line 2 (optional)" />
				</label>
				<label class="field">
					<span>Postal code</span>
					<input v-model="form.pincode" class="input" />
				</label>
				<label class="field">
					<span>City</span>
					<input v-model="form.city" class="input" />
				</label>
				<label class="field">
					<span>IBAN</span>
					<input v-model="form.iban" class="input" />
				</label>
				<label class="field">
					<span>Bank name</span>
					<input v-model="form.bank_name" class="input" placeholder="Optional; derived from the IBAN otherwise" />
				</label>
			</div>
			<p v-if="error" class="mt-3 text-sm text-ink-red-4">{{ error }}</p>
		</template>
	</Dialog>
</template>

<script setup>
import { reactive, ref } from "vue"
import { call, Dialog } from "frappe-ui"
import FrappeLink from "@spa/components/FrappeLink.vue"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	receiptName: { type: String, required: true },
	prefill: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:modelValue", "created"])

const form = reactive({
	supplier_name: props.prefill.supplier_name || "",
	tax_id: props.prefill.tax_id || "",
	tax_category: "",
	supplier_group: "",
	country: props.prefill.country || "",
	address_line1: props.prefill.address_line1 || "",
	address_line2: props.prefill.address_line2 || "",
	pincode: props.prefill.pincode || "",
	city: props.prefill.city || "",
	iban: props.prefill.iban || "",
	bank_name: "",
})
const saving = ref(false)
const error = ref("")
const taxCategoryRequired = ref(false)
call("frappe.client.get_count", { doctype: "Tax Category" })
	.then((count) => (taxCategoryRequired.value = Number(count) > 0))
	.catch(() => {})

async function submit() {
	if (saving.value) return
	error.value = ""
	if (!form.supplier_name.trim()) {
		error.value = "Supplier name is required."
		return
	}
	saving.value = true
	try {
		const receipt = await call("phamos.api.accounting_receipts.create_supplier_from_receipt", {
			name: props.receiptName,
			...form,
		})
		emit("created", receipt)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not create the supplier"
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
