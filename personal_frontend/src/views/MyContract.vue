<template>
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-4xl flex-col gap-5">
			<div v-if="myContracts.error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ myContracts.error }}
			</div>
			<div v-else-if="!myContracts.loaded" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
				{{ __("Loading your contract…") }}
			</div>
			<p v-else-if="!data?.history?.length" class="text-sm text-ink-gray-5">
				{{ __("There is no contract for you yet. HR adds it once it is signed.") }}
			</p>
			<template v-else>
				<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<template v-if="current">
						<div class="flex flex-wrap items-center justify-between gap-3">
							<div>
								<h2 class="text-base font-semibold text-ink-gray-9">{{ __("Current contract") }}</h2>
								<p class="mt-1 text-sm text-ink-gray-6">{{ current.contract_type }} · {{ formatPeriod(current) }}</p>
							</div>
							<ContractStatusBadge :status="current.status" />
						</div>
						<dl class="mt-4 grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
							<div v-for="item in facts(current)" :key="item.label">
								<dt class="text-xs text-ink-gray-5">{{ item.label }}</dt>
								<dd class="mt-1 text-lg font-semibold tabular-nums text-ink-gray-9">{{ item.value }}</dd>
							</div>
						</dl>
					</template>
					<p v-else class="text-sm text-ink-gray-6">{{ __("No contract is in force today.") }}</p>
				</section>

				<section v-if="data.upcoming.length" class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<h2 class="mb-3 text-base font-semibold text-ink-gray-9">{{ __("Upcoming changes") }}</h2>
					<ul class="divide-y divide-outline-gray-1">
						<li v-for="row in data.upcoming" :key="row.name" class="flex flex-wrap items-center justify-between gap-3 py-2 text-sm">
							<span class="text-ink-gray-9">{{ __("From {0}", [formatDate(row.effective_from)]) }}</span>
							<span class="tabular-nums text-ink-gray-7">
								{{
									__("{0} · {1} per week · {2} per month", [
										formatPercent(row.fte_percentage),
										formatHours(row.weekly_hours),
										formatMoney(row.monthly_gross, row.currency),
									])
								}}
							</span>
						</li>
					</ul>
				</section>

				<section>
					<h2 class="mb-2 text-sm font-semibold text-ink-gray-9">{{ __("History") }}</h2>
					<ContractHistoryTable :rows="data.history" :current-name="current?.name || ''" />
				</section>

				<p class="text-xs text-ink-gray-5">{{ __("Something looks wrong? Ask HR to record a change.") }}</p>
			</template>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted } from "vue"
import ContractHistoryTable from "@spa/contracts/ContractHistoryTable.vue"
import ContractStatusBadge from "@spa/contracts/ContractStatusBadge.vue"
import { formatDate, formatHours, formatMoney, formatPercent, formatPeriod } from "@spa/contracts/contractFormat.js"
import { __ } from "@spa/utils/i18n.js"
import { loadMyContracts, myContracts } from "../contractStore.js"

const data = computed(() => myContracts.data)
const current = computed(() => data.value?.current || null)

function facts(contract) {
	const list = [
		{ label: __("FTE"), value: formatPercent(contract.fte_percentage) },
		{ label: __("Hours per week"), value: formatHours(contract.weekly_hours) },
		{ label: __("Monthly gross"), value: formatMoney(contract.monthly_gross, contract.currency) },
	]
	if (contract.contract_type === "Employed") {
		list.push({ label: __("Yearly gross at 100 %"), value: formatMoney(contract.yearly_gross_full_time, contract.currency) })
	}
	return list
}

onMounted(loadMyContracts)
</script>
