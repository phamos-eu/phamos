<template>
	<Dialog
		:options="{
			title: 'Already paid',
			size: 'lg',
			actions: [
				{ label: 'Cancel', variant: 'subtle', onClick: () => emit('update:modelValue', false) },
				{ label: saving ? 'Saving…' : 'Mark as paid', variant: 'solid', loading: saving, disabled: !options, onClick: submit },
			],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<p v-if="!options" class="text-sm text-ink-gray-5">Loading…</p>
			<div v-else class="flex flex-col gap-3 text-sm" @keydown.meta.enter="submit" @keydown.ctrl.enter="submit">
				<p class="text-ink-gray-6">For receipts paid by card, direct debit, PayPal or privately. Nothing is booked; the receipt is marked paid.</p>
				<div class="grid grid-cols-2 gap-3">
					<label class="field">
						<span>Paid on</span>
						<input v-model="form.payment_date" type="date" class="input" />
					</label>
					<label class="field">
						<span>Paid by</span>
						<select v-model="form.mode_of_payment" class="input">
							<option :value="null">—</option>
							<option v-for="mode in options.modes_of_payment" :key="mode" :value="mode">{{ mode }}</option>
						</select>
					</label>
				</div>
				<label class="field">
					<span>From account</span>
					<select v-model="form.bank_account" class="input">
						<option :value="null">— not from a company bank account —</option>
						<option v-for="account in options.bank_accounts" :key="account.name" :value="account.name">
							{{ account.account_name }}{{ account.iban ? ` · ${account.iban}` : "" }}
						</option>
					</select>
				</label>
				<label v-if="options.payment_request" class="flex items-center gap-2">
					<input v-model="form.cancel_payment_request" type="checkbox" />
					<span>Cancel Payment Request {{ options.payment_request }}, it is no longer needed</span>
				</label>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
// "Already paid": record when and how a receipt was paid, outside a Payment Request.
import { reactive, ref, watch } from "vue"
import { call, Dialog, toast } from "frappe-ui"

const API = "phamos.api.accounting_receipts"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	receipt: { type: Object, required: true },
})
const emit = defineEmits(["update:modelValue", "paid"])

const options = ref(null)
const saving = ref(false)
const form = reactive({ payment_date: null, mode_of_payment: null, bank_account: null, cancel_payment_request: true })

function today() {
	const d = new Date()
	return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

async function load() {
	options.value = null
	try {
		const res = await call(`${API}.get_approval_options`, { name: props.receipt.name })
		options.value = res
		Object.assign(form, {
			payment_date: res.payment_date || today(),
			mode_of_payment: props.receipt.mode_of_payment || null,
			bank_account: props.receipt.bank_account || null,
			cancel_payment_request: true,
		})
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "Could not load the payment options", icon: "x-circle", iconClasses: "text-ink-red-4" })
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
		const res = await call(`${API}.mark_receipt_paid`, {
			name: props.receipt.name,
			payment_date: form.payment_date,
			mode_of_payment: form.mode_of_payment,
			bank_account: form.bank_account,
			cancel_payment_request: form.cancel_payment_request ? 1 : 0,
		})
		emit("update:modelValue", false)
		emit("paid", res)
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "Could not mark the receipt as paid", icon: "x-circle", iconClasses: "text-ink-red-4" })
	} finally {
		saving.value = false
	}
}
</script>
