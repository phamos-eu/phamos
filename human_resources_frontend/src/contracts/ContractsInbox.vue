<template>
	<div class="flex h-full min-h-0">
		<section
			v-if="!selectedName"
			class="flex min-w-0 flex-1 flex-col border-r border-outline-gray-2 bg-surface-white"
		>
			<div v-if="loadError" class="flex flex-1 items-center justify-center px-6 text-center text-sm text-ink-red-4">
				{{ loadError }}
			</div>
			<div v-else-if="loading" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
				Loading…
			</div>
			<div v-else :class="[CONTRACT_GRID, 'min-h-0 flex-1 content-start overflow-y-auto px-5']">
				<div :class="[CONTRACT_SUBGRID, 'sticky top-0 z-[1] border-b border-outline-gray-2 bg-surface-white py-3']">
					<FormControl
						ref="searchEl"
						v-model="search"
						type="text"
						size="sm"
						placeholder="Search employee…"
						class="w-full min-w-0"
					/>
					<FormControl
						v-model="typeFilter"
						type="select"
						size="sm"
						:options="[
							{ label: 'All types', value: '' },
							{ label: 'Employed', value: 'Employed' },
							{ label: 'External', value: 'External' },
						]"
						class="w-full min-w-0"
					/>
					<div class="col-span-3 text-xs text-ink-gray-5">{{ filteredRows.length }} contracts</div>
					<FormControl
						v-model="statusFilter"
						type="select"
						size="sm"
						:options="statusOptions"
						class="w-full min-w-0"
					/>
					<div class="flex justify-end">
						<Button v-if="access.can_create" variant="solid" label="New" @click="openDialog('new')" />
					</div>
				</div>

				<div :class="[CONTRACT_SUBGRID, 'py-2 text-xs font-medium text-ink-gray-5']">
					<div>Employee</div>
					<div>Type</div>
					<div>Period</div>
					<div class="text-right">FTE</div>
					<div class="text-right">Weekly</div>
					<div class="text-right">Monthly gross</div>
					<div>Status</div>
				</div>

				<button
					v-for="row in filteredRows"
					:key="row.name"
					type="button"
					:class="[CONTRACT_SUBGRID, 'border-b border-outline-gray-1 py-3 text-left text-sm hover:bg-surface-gray-2 focus:bg-surface-gray-2 focus:outline-none']"
					@click="openContract(row.name)"
				>
					<div class="min-w-0">
						<div class="truncate font-semibold text-ink-gray-9">{{ row.employee_name }}</div>
						<div class="truncate text-xs text-ink-gray-5">{{ row.name }}</div>
					</div>
					<div class="truncate text-ink-gray-8">{{ row.contract_type }}</div>
					<div class="truncate text-ink-gray-8">{{ formatPeriod(row) }}</div>
					<div class="text-right tabular-nums text-ink-gray-8">{{ formatPercent(row.fte_percentage) }}</div>
					<div class="text-right tabular-nums text-ink-gray-8">{{ formatHours(row.weekly_hours) }}</div>
					<div class="text-right tabular-nums text-ink-gray-8">{{ formatMoney(row.monthly_gross, row.currency) }}</div>
					<div><ContractStatusBadge :status="row.status" /></div>
				</button>

				<div v-if="!filteredRows.length" class="col-span-7 py-16 text-center">
					<p class="font-medium text-ink-gray-9">No contracts found</p>
					<p class="mt-1 text-sm text-ink-gray-6">Clear the search or choose "All statuses".</p>
				</div>
			</div>
		</section>

		<section v-else class="flex min-h-0 min-w-0 flex-1 flex-col bg-surface-white">
			<div v-if="detailLoading && !selected" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
				Loading…
			</div>
			<ContractDetail
				v-else-if="selected"
				:contract="selected"
				@close="closeContract"
				@open="openContract"
				@change="(c) => openDialog('change', c)"
				@edit="(c) => openDialog('edit', c)"
				@updated="onSaved"
			/>
		</section>

		<ContractDialog
			v-model="dialogOpen"
			:mode="dialogMode"
			:source="dialogSource"
			:employee="dialogEmployee"
			@saved="onSaved"
		/>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call } from "frappe-ui"
import ContractDetail from "./ContractDetail.vue"
import ContractDialog from "./ContractDialog.vue"
import ContractStatusBadge from "./ContractStatusBadge.vue"
import {
	CONTRACT_GRID,
	CONTRACT_STATUSES,
	CONTRACT_SUBGRID,
	CONTRACTS_API,
	errorMessage,
	formatHours,
	formatMoney,
	formatPercent,
	formatPeriod,
} from "./contractFormat.js"
import { useContractAccess } from "./useContractAccess.js"

const route = useRoute()
const router = useRouter()
const { access } = useContractAccess()

const rows = ref([])
const loading = ref(false)
const loadError = ref("")
const search = ref("")
const typeFilter = ref("")
const statusFilter = ref("current")
const selectedName = ref(null)
const selected = ref(null)
const detailLoading = ref(false)
const dialogOpen = ref(false)
const dialogMode = ref("new")
const dialogSource = ref(null)
const dialogEmployee = ref("")
const searchEl = ref(null)

const statusOptions = [
	{ label: "Current (draft, upcoming, active)", value: "current" },
	{ label: "All statuses", value: "" },
	...CONTRACT_STATUSES.map((s) => ({ label: s, value: s })),
]

const filteredRows = computed(() => {
	const q = search.value.trim().toLowerCase()
	return rows.value.filter((row) => {
		if (statusFilter.value === "current" && !["Draft", "Upcoming", "Active"].includes(row.status)) return false
		if (statusFilter.value && statusFilter.value !== "current" && row.status !== statusFilter.value) return false
		if (typeFilter.value && row.contract_type !== typeFilter.value) return false
		if (q && ![row.employee_name, row.employee, row.name].some((v) => String(v || "").toLowerCase().includes(q)))
			return false
		return true
	})
})

async function loadRows() {
	loading.value = true
	try {
		rows.value = await call(`${CONTRACTS_API}.get_contracts`)
		loadError.value = ""
	} catch (e) {
		loadError.value = errorMessage(e, "Could not load contracts")
	} finally {
		loading.value = false
	}
}

async function openContract(name) {
	selectedName.value = name
	if (route.params.name !== name) router.replace({ name: "ContractDetail", params: { name } })
	detailLoading.value = true
	try {
		selected.value = await call(`${CONTRACTS_API}.get_contract`, { name })
	} catch (e) {
		loadError.value = errorMessage(e, "Could not load the contract")
		closeContract()
	} finally {
		detailLoading.value = false
	}
}

function closeContract() {
	selectedName.value = null
	selected.value = null
	router.replace({ name: "ContractsList" })
}

function openDialog(mode, source = null, employee = "") {
	dialogMode.value = mode
	dialogSource.value = source
	dialogEmployee.value = employee
	dialogOpen.value = true
}

async function onSaved(contract) {
	await loadRows()
	if (contract?.name) await openContract(contract.name)
}

// "/" focuses search and "n" opens a new contract, unless the user is typing somewhere.
function onKeydown(event) {
	const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(event.target?.tagName) || event.target?.isContentEditable
	if (typing || dialogOpen.value || event.metaKey || event.ctrlKey || event.altKey) return
	if (event.key === "/" && !selectedName.value) {
		event.preventDefault()
		searchEl.value?.$el?.querySelector("input")?.focus()
	} else if (event.key === "n" && access.value.can_create) {
		event.preventDefault()
		openDialog("new")
	} else if (event.key === "Escape" && selectedName.value) {
		closeContract()
	}
}

watch(
	() => route.params.name,
	(name) => {
		if (name && name !== selectedName.value) openContract(name)
		if (!name) {
			selectedName.value = null
			selected.value = null
		}
	}
)

onMounted(async () => {
	window.addEventListener("keydown", onKeydown)
	await loadRows()
	if (route.params.name) await openContract(route.params.name)
	// The overview links "employee without contract" here with ?new=<employee>.
	if (route.query.new !== undefined) {
		openDialog("new", null, String(route.query.new || ""))
		router.replace({ query: {} })
	}
})

onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown))
</script>
