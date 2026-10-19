<template>
	<Dialog
		:options="{
			title: 'Approve to pay',
			size: 'lg',
			actions: [
				{ label: 'Cancel', variant: 'subtle', onClick: () => emit('update:modelValue', false) },
				{ label: saving ? 'Approving…' : confirmLabel, variant: 'solid', loading: saving, disabled: !options, onClick: submit },
			],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<p v-if="!options" class="text-sm text-ink-gray-5">Loading…</p>
			<div v-else class="flex flex-col gap-3 text-sm" @keydown.meta.enter="submit" @keydown.ctrl.enter="submit">
				<p class="text-ink-gray-7">
					{{ receipt.supplier_name || receipt.supplier }} · {{ amountText }}
					<span class="text-ink-gray-5">· {{ options.purchase_invoice }}</span>
				</p>
				<label class="field">
					<span>Pay from</span>
					<select v-model="form.bank_account" class="input">
						<option v-for="account in options.bank_accounts" :key="account.name" :value="account.name">
							{{ account.account_name }}{{ account.iban ? ` · ${account.iban}` : "" }}
						</option>
					</select>
					<span v-if="!options.bank_accounts.length" class="text-xs text-ink-amber-3">
						The company has no bank account in ERPNext yet (Bank Account with "Is Company Account").
					</span>
				</label>
				<div class="grid grid-cols-2 gap-3">
					<label class="field">
						<span>Mode of payment</span>
						<select v-model="form.mode_of_payment" class="input">
							<option v-for="mode in options.modes_of_payment" :key="mode" :value="mode">{{ mode }}</option>
						</select>
					</label>
					<label class="field">
						<span>Pay by</span>
						<input v-model="form.due_date" type="date" class="input" />
					</label>
				</div>
				<label class="flex items-center gap-2" :class="{ 'opacity-60': options.payment_request }">
					<input v-model="form.create_payment_request" type="checkbox" :disabled="!!options.payment_request || !options.can_create_payment_request" />
					<span v-if="options.payment_request">Payment Request {{ options.payment_request }} already exists</span>
					<span v-else>Create a Payment Request</span>
				</label>
				<template v-if="form.create_payment_request && !options.payment_request">
					<p v-if="options.supplier_bank_account" class="text-xs text-ink-gray-5">Pays to {{ options.supplier_iban || options.supplier_bank_account }}.</p>
					<label v-else-if="options.receipt_iban_valid" class="flex items-start gap-2 text-xs">
						<input v-model="form.save_supplier_iban" type="checkbox" class="mt-0.5" />
						<span>Save {{ options.receipt_iban }} from the receipt as the supplier's bank account, so the Payment Request pays there.</span>
					</label>
					<p v-else class="text-xs text-ink-amber-3">
						The supplier has no bank account in ERPNext, so the Payment Request has no IBAN to pay to.
						{{ options.receipt_iban ? `The receipt's IBAN ${options.receipt_iban} is not valid.` : "Add the IBAN to the receipt to save it here." }}
					</p>
				</template>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
// Approve a receipt to pay: choose the paying account, mode and date; the server sets the
// status and creates the Payment Request for the submitted Purchase Invoice.
import { computed, reactive, ref, watch } from "vue"
import { call, Dialog, toast } from "frappe-ui"

const API = "phamos.api.accounting_receipts"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	receipt: { type: Object, required: true },
})
const emit = defineEmits(["update:modelValue", "approved"])

const options = ref(null)
const saving = ref(false)
const form = reactive({ bank_account: null, mode_of_payment: null, due_date: null, create_payment_request: true, save_supplier_iban: true })

const amountText = computed(() => {
	const amount = options.value?.outstanding_amount ?? props.receipt.sum
	try {
		return new Intl.NumberFormat(undefined, { style: "currency", currency: options.value?.currency || props.receipt.currency || "EUR" }).format(amount || 0)
	} catch (e) {
		return String(amount)
	}
})
const confirmLabel = computed(() => (form.create_payment_request && !options.value?.payment_request ? "Approve and request payment" : "Approve"))

async function load() {
	options.value = null
	try {
		const res = await call(`${API}.get_approval_options`, { name: props.receipt.name })
		options.value = res
		Object.assign(form, {
			bank_account: res.bank_account,
			mode_of_payment: res.mode_of_payment,
			due_date: res.due_date,
			create_payment_request: !res.payment_request && !!res.can_create_payment_request,
			save_supplier_iban: !res.supplier_bank_account && !!res.receipt_iban_valid,
		})
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "Could not load the approval options", icon: "x-circle", iconClasses: "text-ink-red-4" })
		emit("update:modelValue", false)
	}
}

watch(
	() => props.modelValue,
	(open) => open && load(),
	{ immediate: true }
)

async function submit() {
	if (saving.value || !options.value) return
	saving.value = true
	try {
		const res = await call(`${API}.approve_receipt`, {
			name: props.receipt.name,
			bank_account: form.bank_account,
			mode_of_payment: form.mode_of_payment,
			due_date: form.due_date,
			create_payment_request: form.create_payment_request ? 1 : 0,
			save_supplier_iban: form.save_supplier_iban && !options.value.supplier_bank_account ? 1 : 0,
		})
		emit("update:modelValue", false)
		emit("approved", res)
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "Could not approve the receipt", icon: "x-circle", iconClasses: "text-ink-red-4" })
	} finally {
		saving.value = false
	}
}
</script>
