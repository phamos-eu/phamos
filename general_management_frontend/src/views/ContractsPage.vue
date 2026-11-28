<template>
	<!-- Contracts (#2148): ERPNext's standard Contract, typed by Contract Type (AVV, NDA, ...).
	     Read-only list for now; a row opens the contract in Desk. -->
	<div class="flex h-full min-h-0 flex-col bg-surface-white dark:bg-surface-gray-1">
		<div class="flex flex-shrink-0 flex-wrap items-end gap-2 border-b border-outline-gray-2 bg-surface-gray-1 px-3 py-2 dark:bg-surface-gray-2">
			<FormControl v-model="contractType" :label="__('Type')" type="select" size="sm" :options="typeOptions" />
			<FormControl v-model="status" :label="__('Status')" type="select" size="sm" :options="statusOptions" />
			<FormControl v-model="ending" :label="__('Ends within')" type="select" size="sm" :options="endingOptions" />
			<FormControl v-model="party" :label="__('Party')" type="text" size="sm" :placeholder="__('Search party')" />
			<span class="ml-auto self-center text-xs text-ink-gray-5">{{ countLabel }}</span>
		</div>

		<div v-if="error" class="flex flex-1 items-center justify-center px-6 text-center text-sm text-ink-red-4">
			{{ error }}
		</div>
		<div v-else-if="loading && !loaded" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
			{{ __("Loading…") }}
		</div>
		<div v-else class="min-h-0 flex-1 overflow-y-auto">
			<div v-if="!contracts.length" class="px-6 py-10 text-center text-sm text-ink-gray-5">
				{{ __("No contracts") }}
			</div>
			<table v-else class="w-full text-left text-sm">
				<thead class="sticky top-0 bg-surface-white text-xs text-ink-gray-5 dark:bg-surface-gray-1">
					<tr class="border-b border-outline-gray-2">
						<th class="px-4 py-2 font-medium">{{ __("Type") }}</th>
						<th class="px-4 py-2 font-medium">{{ __("Party") }}</th>
						<th class="px-4 py-2 font-medium">{{ __("Status") }}</th>
						<th class="px-4 py-2 font-medium">{{ __("Signed") }}</th>
						<th class="px-4 py-2 font-medium">{{ __("Start") }}</th>
						<th class="px-4 py-2 font-medium">{{ __("End") }}</th>
					</tr>
				</thead>
				<tbody>
					<tr
						v-for="contract in contracts"
						:key="contract.name"
						class="cursor-pointer border-b border-outline-gray-1 hover:bg-surface-gray-2"
						:title="__('Open in Desk')"
						@click="openInDesk(contract)"
					>
						<td class="px-4 py-2 text-ink-gray-9">{{ contract.custom_contract_type || "–" }}</td>
						<td class="px-4 py-2">
							<div class="truncate font-medium text-ink-gray-9">
								{{ contract.party_full_name || contract.party_name }}
							</div>
							<div class="text-xs text-ink-gray-5">{{ __(contract.party_type) }}</div>
						</td>
						<td class="px-4 py-2">
							<span :class="STATUS_CLASS[contract.status] || 'text-ink-gray-5'">{{ __(contract.status) }}</span>
						</td>
						<td class="px-4 py-2 text-ink-gray-7">{{ contract.is_signed ? __("Yes") : __("No") }}</td>
						<td class="px-4 py-2 text-ink-gray-7">{{ contract.start_date ? formatDate(contract.start_date) : "–" }}</td>
						<td class="px-4 py-2 text-ink-gray-7">{{ contract.end_date ? formatDate(contract.end_date) : "–" }}</td>
					</tr>
				</tbody>
			</table>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { call, FormControl } from "frappe-ui"
import { formatDate } from "@spa/utils/datetime"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "@/config"

const STATUS_CLASS = {
	Active: "text-ink-green-4",
	Unsigned: "text-ink-amber-3",
	Inactive: "text-ink-gray-5",
}

const contracts = ref([])
// Row cap of get_contracts; at the cap the count reads "500+" so it is not taken as the total.
const limit = ref(0)
const countLabel = computed(() =>
	limit.value && contracts.value.length >= limit.value
		? __("{0}+ contracts", [limit.value])
		: __("{0} contracts", [contracts.value.length]),
)
const types = ref([])
const statuses = ref([])
const contractType = ref("")
const status = ref("")
const ending = ref("")
const party = ref("")
const loading = ref(false)
const loaded = ref(false)
const error = ref("")

const typeOptions = computed(() => [
	{ label: __("All types"), value: "" },
	...types.value.map((name) => ({ label: name, value: name })),
])
const statusOptions = computed(() => [
	{ label: __("All statuses"), value: "" },
	...statuses.value.map((name) => ({ label: __(name), value: name })),
])
const endingOptions = computed(() => [
	{ label: __("Any time"), value: "" },
	{ label: __("{0} days", [30]), value: "30" },
	{ label: __("{0} days", [60]), value: "60" },
	{ label: __("{0} days", [90]), value: "90" },
])

let requestId = 0
async function load() {
	const mine = ++requestId
	loading.value = true
	try {
		const rows = await call(`${spaConfig.api}.get_contracts`, {
			contract_type: contractType.value || null,
			status: status.value || null,
			party: party.value.trim() || null,
			ending_within_days: ending.value || null,
		})
		if (mine !== requestId) return
		contracts.value = rows || []
		error.value = ""
		loaded.value = true
	} catch (e) {
		if (mine !== requestId) return
		error.value = e?.messages?.[0] || e?.message || __("Could not load the contracts")
	} finally {
		if (mine === requestId) loading.value = false
	}
}

let partyTimer = null
watch([contractType, status, ending], load)
watch(party, () => {
	clearTimeout(partyTimer)
	partyTimer = setTimeout(load, 300)
})

function openInDesk(contract) {
	window.open(`/app/contract/${encodeURIComponent(contract.name)}`, "_blank", "noopener")
}

onMounted(async () => {
	try {
		const options = await call(`${spaConfig.api}.get_contract_options`)
		types.value = options?.types || []
		statuses.value = options?.statuses || []
		limit.value = options?.limit || 0
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not load the contracts")
		return
	}
	load()
})
</script>
