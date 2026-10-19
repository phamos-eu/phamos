<template>
	<Dialog
		:options="{
			title: kind === 'expense_claim' ? 'Book as Expense Claim' : 'Book as Journal Entry',
			size: 'xl',
			actions: [
				{ label: 'Cancel', variant: 'subtle', onClick: () => emit('update:modelValue', false) },
				{ label: saving ? 'Creating…' : 'Create draft', variant: 'solid', loading: saving, disabled: !canSubmit, onClick: submit },
			],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<p v-if="!options" class="text-sm text-ink-gray-5">Loading…</p>
			<div v-else class="flex flex-col gap-3 text-sm" @keydown.meta.enter="submit" @keydown.ctrl.enter="submit">
				<p class="text-ink-gray-6">
					<template v-if="kind === 'expense_claim'">For a receipt an employee paid privately: the Expense Claim reimburses them. It is created as a draft for the approver.</template>
					<template v-else>For a voucher without a supplier invoice, such as a tax notice, bank fees or a card statement. It is created as a draft.</template>
				</p>

				<div v-if="kind === 'expense_claim'" class="grid grid-cols-2 gap-3">
					<label class="field">
						<span>Paid by *</span>
						<FrappeLink v-model="form.employee" doctype="Employee" :filters="{ status: 'Active' }" placeholder="Employee" />
					</label>
					<label class="field">
						<span>Expense type</span>
						<select v-model="form.expense_type" class="input">
							<option v-for="type in options.expense_types" :key="type" :value="type">{{ type }}</option>
						</select>
						<span class="text-xs text-ink-gray-5">Used when no type is booked on a line's account.</span>
					</label>
				</div>
				<label v-else class="field">
					<span>Credit account *</span>
					<FrappeLink
						v-model="form.credit_account"
						doctype="Account"
						:filters="{ is_group: 0, disabled: 0, account_type: ['not in', ['Payable', 'Receivable']], ...(receipt.company ? { company: receipt.company } : {}) }"
						placeholder="Bank it was paid from, or what is owed"
					/>
				</label>

				<p v-if="options.split_error" class="text-ink-red-4">{{ options.split_error }}</p>
				<table v-else-if="options.split" class="w-full text-sm">
					<thead>
						<tr class="text-left text-[11px] uppercase tracking-wide text-ink-gray-5">
							<th class="py-1 pr-2">Debit</th>
							<th class="py-1 pr-2">Account</th>
							<th class="w-24 py-1 text-right">Amount</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="(row, i) in options.split.lines" :key="`l${i}`" class="border-t border-outline-gray-1">
							<td class="truncate py-1 pr-2">{{ row.description }}</td>
							<td class="truncate py-1 pr-2 text-ink-gray-6">{{ accountLabel(row.account) }}</td>
							<td class="py-1 text-right tabular-nums">{{ money(row.net) }}</td>
						</tr>
						<tr v-for="(tax, i) in options.split.taxes" :key="`t${i}`" class="border-t border-outline-gray-1 text-ink-gray-6">
							<td class="py-1 pr-2">Input VAT {{ tax.rate }} %</td>
							<td class="truncate py-1 pr-2">{{ accountLabel(tax.account) }}</td>
							<td class="py-1 text-right tabular-nums">{{ money(tax.amount) }}</td>
						</tr>
						<tr class="border-t border-outline-gray-2 font-medium">
							<td class="py-1 pr-2">{{ kind === "expense_claim" ? "Owed to the employee" : "Credit" }}</td>
							<td class="truncate py-1 pr-2 text-ink-gray-6">{{ kind === "expense_claim" ? "Expense claim payable" : accountLabel(form.credit_account) }}</td>
							<td class="py-1 text-right tabular-nums">{{ money(options.split.total) }}</td>
						</tr>
					</tbody>
				</table>
				<p v-if="options.split" class="text-xs text-ink-gray-5">
					The lines hold {{ options.split.lines_are_gross ? "gross" : "net" }} amounts; the VAT is split off by each line's tax rate.
				</p>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
// Book a receipt as a draft Expense Claim or Journal Entry, with a preview of the postings.
import { computed, reactive, ref, watch } from "vue"
import { call, Dialog, toast } from "frappe-ui"
import FrappeLink from "@spa/components/FrappeLink.vue"

const API = "phamos.api.accounting_receipts"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	receipt: { type: Object, required: true },
	kind: { type: String, required: true }, // expense_claim | journal_entry
})
const emit = defineEmits(["update:modelValue", "booked"])

const options = ref(null)
const saving = ref(false)
const form = reactive({ employee: null, expense_type: null, credit_account: null })

const canSubmit = computed(() => {
	if (!options.value || options.value.split_error) return false
	return props.kind === "expense_claim" ? !!form.employee : !!form.credit_account
})

function accountLabel(account) {
	return (account || "").replace(/ - [^-]+$/, "")
}

function money(value) {
	try {
		return new Intl.NumberFormat(undefined, { style: "currency", currency: props.receipt.currency || "EUR" }).format(value || 0)
	} catch (e) {
		return String(value)
	}
}

async function load() {
	options.value = null
	try {
		const res = await call(`${API}.get_booking_options`, { name: props.receipt.name })
		options.value = res
		Object.assign(form, { employee: res.employee, expense_type: res.expense_type, credit_account: res.credit_account })
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "Could not load the booking options", icon: "x-circle", iconClasses: "text-ink-red-4" })
		emit("update:modelValue", false)
	}
}

watch(
	() => props.modelValue,
	(open) => open && load(),
	{ immediate: true }
)

async function submit() {
	if (saving.value || !canSubmit.value) return
	saving.value = true
	try {
		const res =
			props.kind === "expense_claim"
				? await call(`${API}.make_expense_claim`, { name: props.receipt.name, employee: form.employee, expense_type: form.expense_type })
				: await call(`${API}.make_journal_entry`, { name: props.receipt.name, credit_account: form.credit_account })
		emit("update:modelValue", false)
		emit("booked", res)
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "Could not create the draft", icon: "x-circle", iconClasses: "text-ink-red-4" })
	} finally {
		saving.value = false
	}
}
</script>
