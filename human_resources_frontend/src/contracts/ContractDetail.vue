<template>
	<div class="flex h-full min-h-0 w-full flex-1 flex-col overflow-hidden">
		<div class="flex items-start justify-between gap-3 border-b border-outline-gray-2 px-5 py-4">
			<div class="min-w-0">
				<div class="text-xs font-semibold text-ink-gray-6">{{ contract.name }}</div>
				<h2 class="mt-1 truncate text-lg font-semibold text-ink-gray-9">{{ contract.employee_name }}</h2>
				<div class="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-gray-6">
					<ContractStatusBadge :status="contract.status" />
					<span>{{ contract.contract_type }} · {{ formatPeriod(contract) }}</span>
				</div>
			</div>
			<div class="flex flex-shrink-0 items-center gap-2">
				<Button v-if="contract.can_record_change" variant="solid" label="Record change" @click="emit('change', contract)" />
				<template v-if="contract.can_edit">
					<Button label="Edit" @click="emit('edit', contract)" />
					<Button variant="solid" label="Submit" :loading="submitting" @click="submit" />
				</template>
				<Button variant="ghost" label="Close" @click="emit('close')" />
			</div>
		</div>

		<div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
			<ErrorMessage :message="error" class="mb-3" />
			<dl class="grid grid-cols-2 gap-4 text-sm lg:grid-cols-3">
				<div v-for="item in facts" :key="item.label">
					<dt class="text-xs text-ink-gray-5">{{ item.label }}</dt>
					<dd class="mt-1 font-medium tabular-nums text-ink-gray-9">{{ item.value }}</dd>
				</div>
			</dl>
			<p v-if="contract.superseded_by" class="mt-4 text-sm text-ink-gray-6">
				Superseded by
				<button type="button" class="font-medium text-ink-gray-9 underline" @click="emit('open', contract.superseded_by)">
					{{ contract.superseded_by }}
				</button>
			</p>
			<p v-if="contract.notes" class="mt-4 whitespace-pre-line text-sm text-ink-gray-8">{{ contract.notes }}</p>

			<h3 class="mb-2 mt-6 text-sm font-semibold text-ink-gray-9">History</h3>
			<ContractHistoryTable
				:rows="contract.history"
				:current-name="contract.name"
				clickable
				@open="(name) => emit('open', name)"
			/>

			<a
				:href="contract.desk_url"
				class="mt-6 inline-flex items-center gap-2 text-sm font-medium text-ink-gray-7 hover:text-ink-gray-9"
			>
				<FeatherIcon name="external-link" class="h-4 w-4" />
				Open in Desk
			</a>
		</div>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { call, toast } from "frappe-ui"
import ContractHistoryTable from "@spa/contracts/ContractHistoryTable.vue"
import ContractStatusBadge from "@spa/contracts/ContractStatusBadge.vue"
import {
	CONTRACTS_API,
	errorMessage,
	formatHours,
	formatMoney,
	formatRate,
	formatPercent,
	formatPeriod,
} from "@spa/contracts/contractFormat.js"

const props = defineProps({ contract: { type: Object, required: true } })
const emit = defineEmits(["close", "change", "edit", "open", "updated"])

const submitting = ref(false)
const error = ref("")

const facts = computed(() => {
	const c = props.contract
	const list = [
		{ label: "FTE", value: formatPercent(c.fte_percentage) },
		{ label: "Weekly hours", value: `${formatHours(c.weekly_hours)} of ${formatHours(c.full_time_hours_per_week)}` },
		{ label: "Monthly gross", value: formatMoney(c.monthly_gross, c.currency) },
	]
	if (c.contract_type === "Employed") {
		list.push({ label: "Yearly gross (100 %)", value: formatMoney(c.yearly_gross_full_time, c.currency) })
	}
	if (c.company_currency && c.currency !== c.company_currency) {
		list.push({ label: "Planning rate", value: `1 ${c.currency} = ${formatRate(c.conversion_rate)} ${c.company_currency}` })
		list.push({ label: `Monthly gross (${c.company_currency})`, value: formatMoney(c.base_monthly_gross, c.company_currency) })
	}
	list.push({ label: "Company", value: c.company || "—" })
	list.push({ label: "Expense account", value: c.expense_account || "—" })
	return list
})

async function submit() {
	submitting.value = true
	error.value = ""
	try {
		const updated = await call(`${CONTRACTS_API}.submit_contract`, { name: props.contract.name })
		toast.success(`Contract ${updated.name} submitted`)
		emit("updated", updated)
	} catch (e) {
		error.value = errorMessage(e, "Could not submit the contract")
	} finally {
		submitting.value = false
	}
}
</script>
