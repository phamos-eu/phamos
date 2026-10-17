<template>
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-7xl flex-col gap-5">
			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ error }}
			</div>
			<div v-else-if="loading" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
				Loading contracts…
			</div>
			<template v-else>
				<div class="flex items-center justify-between gap-3">
					<p class="text-sm text-ink-gray-6">As of {{ formatDate(data.today) }}</p>
					<Button
						v-if="access.can_create"
						variant="solid"
						label="New contract"
						@click="router.push({ name: 'ContractsList', query: { new: '' } })"
					/>
				</div>

				<section class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
					<StatCard
						label="Active FTE"
						:value="formatNumber(data.active_fte)"
						:hint="`${data.active_people} people, ${data.external_people} external`"
					/>
					<StatCard
						label="Monthly personnel cost"
						:value="data.monthly_cost.length ? formatMoney(data.monthly_cost[0].amount, data.monthly_cost[0].currency) : '—'"
						hint="Gross in company currency at each contract's planning rate"
						:lines="data.monthly_cost.slice(1).map((c) => `+ ${formatMoney(c.amount, c.currency)}`)"
					/>
					<StatCard
						:label="`Ending in ${data.ending_soon_days} days`"
						:value="data.ending_soon.length"
						hint="Fixed-term contracts without a follow-up"
					/>
					<StatCard label="Upcoming changes" :value="data.upcoming.length" hint="Submitted, not yet in force" />
					<StatCard
						label="Without contract"
						:value="data.without_contract.length"
						hint="Active employees with no contract"
						:lines="data.drafts ? [`${data.drafts} draft contracts waiting`] : []"
					/>
				</section>

				<div class="grid grid-cols-1 gap-5 xl:grid-cols-3">
					<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
						<h2 class="text-base font-semibold text-ink-gray-9">Ending soon</h2>
						<p class="mb-3 text-sm text-ink-gray-5">Decide on renewal before the end date.</p>
						<p v-if="!data.ending_soon.length" class="text-sm text-ink-gray-5">Nothing ends in the next {{ data.ending_soon_days }} days.</p>
						<button
							v-for="row in data.ending_soon"
							:key="row.name"
							type="button"
							class="flex w-full items-center justify-between gap-3 rounded-md px-2 py-2 text-left text-sm hover:bg-surface-gray-2 focus:bg-surface-gray-2 focus:outline-none"
							@click="openContract(row.name)"
						>
							<span class="truncate font-medium text-ink-gray-9">{{ row.employee_name }}</span>
							<span class="whitespace-nowrap tabular-nums text-ink-gray-6">{{ formatDate(row.valid_until) }}</span>
						</button>
					</section>

					<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
						<h2 class="text-base font-semibold text-ink-gray-9">Upcoming changes</h2>
						<p class="mb-3 text-sm text-ink-gray-5">Brief team leads before capacity shifts.</p>
						<p v-if="!data.upcoming.length" class="text-sm text-ink-gray-5">No changes scheduled.</p>
						<button
							v-for="row in data.upcoming"
							:key="row.name"
							type="button"
							class="flex w-full items-center justify-between gap-3 rounded-md px-2 py-2 text-left text-sm hover:bg-surface-gray-2 focus:bg-surface-gray-2 focus:outline-none"
							@click="openContract(row.name)"
						>
							<span class="min-w-0">
								<span class="block truncate font-medium text-ink-gray-9">{{ row.employee_name }}</span>
								<span class="block text-xs text-ink-gray-5">{{ formatPercent(row.fte_percentage) }} · {{ formatHours(row.weekly_hours) }}</span>
							</span>
							<span class="whitespace-nowrap tabular-nums text-ink-gray-6">{{ formatDate(row.effective_from) }}</span>
						</button>
					</section>

					<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
						<h2 class="text-base font-semibold text-ink-gray-9">Without contract</h2>
						<p class="mb-3 text-sm text-ink-gray-5">Active employees that capacity and cost can't see yet.</p>
						<p v-if="!data.without_contract.length" class="text-sm text-ink-gray-5">Every active employee has a contract.</p>
						<div class="max-h-80 overflow-y-auto">
							<button
								v-for="row in data.without_contract"
								:key="row.employee"
								type="button"
								class="flex w-full items-center justify-between gap-3 rounded-md px-2 py-2 text-left text-sm hover:bg-surface-gray-2 focus:bg-surface-gray-2 focus:outline-none"
								:disabled="!access.can_create"
								@click="router.push({ name: 'ContractsList', query: { new: row.employee } })"
							>
								<span class="truncate font-medium text-ink-gray-9">{{ row.employee_name }}</span>
								<span v-if="access.can_create" class="whitespace-nowrap text-xs text-ink-gray-5">Create →</span>
							</button>
						</div>
					</section>
				</div>
			</template>
		</div>
	</div>
</template>

<script setup>
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { call } from "frappe-ui"
import StatCard from "@spa/components/dashboard/StatCard.vue"
import {
	CONTRACTS_API,
	errorMessage,
	formatDate,
	formatHours,
	formatMoney,
	formatNumber,
	formatPercent,
} from "@spa/contracts/contractFormat.js"
import { useContractAccess } from "./useContractAccess.js"

const router = useRouter()
const { access } = useContractAccess()
const loading = ref(true)
const error = ref("")
const data = ref(null)

function openContract(name) {
	router.push({ name: "ContractDetail", params: { name } })
}

onMounted(async () => {
	try {
		data.value = await call(`${CONTRACTS_API}.get_overview`)
	} catch (e) {
		error.value = errorMessage(e, "Could not load contracts")
	} finally {
		loading.value = false
	}
})
</script>
