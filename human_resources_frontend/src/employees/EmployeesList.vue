<template>
	<div class="flex h-full min-h-0 flex-col overflow-y-auto bg-surface-white">
		<div class="flex flex-wrap items-center gap-3 border-b border-outline-gray-2 px-5 py-3">
			<FormControl
				ref="searchEl"
				v-model="search"
				type="text"
				size="sm"
				placeholder="Search employee…"
				class="w-56"
			/>
			<FormControl v-model="status" type="select" size="sm" :options="statusOptions" class="w-36" />
			<FormControl
				v-if="data.companies.length > 1"
				v-model="company"
				type="select"
				size="sm"
				:options="companyOptions"
				class="w-48"
			/>
			<div class="text-xs text-ink-gray-5">{{ rows.length }} employees</div>
		</div>

		<div v-if="loadError" class="flex flex-1 items-center justify-center px-6 text-center text-sm text-ink-red-4">
			{{ loadError }}
		</div>
		<div v-else-if="loading && !loaded" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
			Loading…
		</div>
		<template v-else>
			<!-- Totals per leave type; never added up across types (#1833, Decision 6). -->
			<section class="grid grid-cols-2 gap-3 px-5 py-4 md:grid-cols-4 xl:grid-cols-6">
				<div
					v-for="total in totals"
					:key="total.leave_type"
					class="rounded-lg border border-outline-gray-2 p-3"
				>
					<div class="truncate text-xs text-ink-gray-5" :title="total.leave_type">{{ total.leave_type }} left</div>
					<div class="mt-1 text-xl font-semibold tabular-nums text-ink-gray-9">{{ formatNumber(total.left) }}</div>
					<div v-if="showYearEndWarning" class="mt-1 text-xs" :class="total.many_left ? 'text-ink-amber-3' : 'text-ink-gray-5'">
						{{ total.many_left }} with more than {{ MANY_DAYS_LEFT }} days
					</div>
				</div>
				<div class="rounded-lg border border-outline-gray-2 p-3">
					<div class="truncate text-xs text-ink-gray-5">No leave in {{ NO_LEAVE_MONTHS }} months</div>
					<div class="mt-1 text-xl font-semibold tabular-nums text-ink-gray-9">{{ noRecentLeave }}</div>
					<div class="mt-1 text-xs text-ink-gray-5">sick leave not counted</div>
				</div>
			</section>

			<!-- Margin, not padding: rows scrolled sideways must not show beside the fixed Employee column. -->
			<div class="mx-5 mb-6 min-h-0 flex-1 overflow-x-auto">
				<table class="w-full border-separate border-spacing-0 text-sm">
					<thead class="sticky top-0 z-[2] bg-surface-white text-xs font-medium text-ink-gray-5">
						<tr>
							<th :class="[stickyCell, headCell, 'text-left']" rowspan="2">
								<button type="button" @click="sortBy('employee_name')">Employee {{ sortMark("employee_name") }}</button>
							</th>
							<th :class="[headCell, 'text-right']" rowspan="2">
								<button type="button" @click="sortBy('years_in_company')">Years {{ sortMark("years_in_company") }}</button>
							</th>
							<th :class="[headCell, 'text-left']" rowspan="2">
								<button type="button" @click="sortBy('birthday')">Birthday {{ sortMark("birthday") }}</button>
							</th>
							<th
								v-for="leaveType in data.leave_types"
								:key="leaveType"
								:class="[headCell, 'border-l border-outline-gray-1 text-center']"
								colspan="2"
							>
								{{ leaveType }}
							</th>
							<th :class="[headCell, 'border-l border-outline-gray-1 text-left']" rowspan="2">
								<button type="button" @click="sortBy('last_leave')">Last leave {{ sortMark("last_leave") }}</button>
							</th>
							<th :class="[headCell, 'text-left']" rowspan="2">
								<button type="button" @click="sortBy('next_leave')">Next leave {{ sortMark("next_leave") }}</button>
							</th>
							<th :class="[headCell, 'text-right']" rowspan="2" title="Leave applications waiting for approval">
								<button type="button" @click="sortBy('pending_count')">Waiting {{ sortMark("pending_count") }}</button>
							</th>
							<th
								v-if="data.can_see_sick_days"
								:class="[headCell, 'text-right']"
								rowspan="2"
								title="Approved sick days this year. Only HR Manager sees this column."
							>
								<button type="button" @click="sortBy('sick_days')">Sick days {{ sortMark("sick_days") }}</button>
							</th>
							<template v-if="data.can_see_contracts">
								<th :class="[headCell, 'border-l border-outline-gray-1 text-right']" rowspan="2">
									<button type="button" @click="sortBy('fte_percentage')">FTE {{ sortMark("fte_percentage") }}</button>
								</th>
								<th :class="[headCell, 'text-left']" rowspan="2">
									<button type="button" @click="sortBy('contract_end')">Contract end {{ sortMark("contract_end") }}</button>
								</th>
							</template>
						</tr>
						<tr>
							<template v-for="leaveType in data.leave_types" :key="leaveType">
								<th :class="[headCell, 'border-l border-outline-gray-1 text-right']">
									<button type="button" @click="sortBy(`left:${leaveType}`)">Left {{ sortMark(`left:${leaveType}`) }}</button>
								</th>
								<th :class="[headCell, 'text-right']">Taken / alloc.</th>
							</template>
						</tr>
					</thead>
					<tbody>
						<tr v-for="row in sortedRows" :key="row.employee" class="hover:bg-surface-gray-1">
							<td :class="[stickyCell, bodyCell]">
								<div class="truncate font-semibold text-ink-gray-9">{{ row.employee_name }}</div>
								<div class="truncate text-xs text-ink-gray-5">
									{{ [row.department, row.designation].filter(Boolean).join(" · ") || row.employee }}
								</div>
							</td>
							<td :class="[bodyCell, 'text-right tabular-nums']">{{ formatNumber(row.years_in_company) }}</td>
							<td :class="[bodyCell, 'tabular-nums']">{{ formatBirthday(row.birthday) }}</td>
							<template v-for="leaveType in data.leave_types" :key="leaveType">
								<td :class="[bodyCell, 'border-l border-outline-gray-1 text-right font-medium tabular-nums text-ink-gray-9']">
									{{ row.leave[leaveType] ? formatNumber(row.leave[leaveType].left) : "—" }}
								</td>
								<td :class="[bodyCell, 'text-right tabular-nums text-ink-gray-6']">
									<template v-if="row.leave[leaveType]">
										{{ formatNumber(row.leave[leaveType].taken) }} / {{ formatNumber(row.leave[leaveType].allocated) }}
									</template>
									<template v-else>—</template>
								</td>
							</template>
							<td :class="[bodyCell, 'border-l border-outline-gray-1 tabular-nums']">{{ formatDate(row.last_leave) || "—" }}</td>
							<td :class="[bodyCell, 'tabular-nums']">{{ formatDate(row.next_leave) || "—" }}</td>
							<td :class="[bodyCell, 'text-right tabular-nums']">{{ row.pending_count || "—" }}</td>
							<td v-if="data.can_see_sick_days" :class="[bodyCell, 'text-right tabular-nums']">
								<span v-if="!data.sick_types_configured" title="Choose the sick leave types in phamos Settings → Human Resources Cockpit">—</span>
								<template v-else>{{ formatNumber(row.sick_days) }}</template>
							</td>
							<template v-if="data.can_see_contracts">
								<td :class="[bodyCell, 'border-l border-outline-gray-1 text-right tabular-nums']">
									{{ row.fte_percentage == null ? "—" : formatPercent(row.fte_percentage) }}
								</td>
								<td :class="[bodyCell, 'tabular-nums']">
									{{ row.fte_percentage == null ? "—" : formatDate(row.contract_end) || "open" }}
								</td>
							</template>
						</tr>
					</tbody>
				</table>
				<div v-if="!sortedRows.length" class="py-16 text-center">
					<p class="font-medium text-ink-gray-9">No employees found</p>
					<p class="mt-1 text-sm text-ink-gray-6">Clear the search or choose another status.</p>
				</div>
				<p v-if="!data.leave_types.length && sortedRows.length" class="mt-4 text-sm text-ink-gray-5">
					No leave is allocated yet, so there are no leave columns. Leave Allocations come from HRMS.
				</p>
			</div>
		</template>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { call } from "frappe-ui"
import { errorMessage, formatDate, formatNumber, formatPercent } from "@spa/contracts/contractFormat.js"
import { getDateFormat } from "@spa/utils/datetime.js"

// Employees list with leave statistics (#1835). Sick days and contract figures come only for
// the roles allowed to see them (#1833, Decisions 2 and 4); the API leaves them out otherwise.
const API = "phamos.api.hr_employees"
const MANY_DAYS_LEFT = 10
const NO_LEAVE_MONTHS = 6

const headCell = "border-b border-outline-gray-2 px-3 py-2 whitespace-nowrap"
const bodyCell = "border-b border-outline-gray-1 px-3 py-2 whitespace-nowrap"
const stickyCell = "sticky left-0 z-[1] min-w-56 max-w-72 bg-surface-white"

const data = ref({
	employees: [],
	leave_types: [],
	companies: [],
	can_see_sick_days: false,
	can_see_contracts: false,
	sick_types_configured: false,
})
const loading = ref(false)
const loaded = ref(false)
const loadError = ref("")
const search = ref("")
const status = ref("Active")
const company = ref("")
const sortKey = ref("employee_name")
const sortAsc = ref(true)
const searchEl = ref(null)

const statusOptions = [
	{ label: "Active", value: "Active" },
	{ label: "Left", value: "Left" },
	{ label: "All", value: "All" },
]
const companyOptions = computed(() => [
	{ label: "All companies", value: "" },
	...data.value.companies.map((c) => ({ label: c, value: c })),
])

const rows = computed(() => {
	const q = search.value.trim().toLowerCase()
	if (!q) return data.value.employees
	return data.value.employees.filter((row) =>
		[row.employee_name, row.employee, row.department, row.designation].some((v) =>
			String(v || "").toLowerCase().includes(q)
		)
	)
})

function sortValue(row, key) {
	if (key.startsWith("left:")) return row.leave[key.slice(5)]?.left ?? null
	return row[key] ?? null
}

const sortedRows = computed(() => {
	const key = sortKey.value
	const direction = sortAsc.value ? 1 : -1
	return [...rows.value].sort((a, b) => {
		const x = sortValue(a, key)
		const y = sortValue(b, key)
		if (x === y) return 0
		if (x === null) return 1 // empty values last, in both directions
		if (y === null) return -1
		return (typeof x === "number" ? x - y : String(x).localeCompare(String(y))) * direction
	})
})

function sortBy(key) {
	if (sortKey.value === key) sortAsc.value = !sortAsc.value
	else {
		sortKey.value = key
		sortAsc.value = true
	}
}

function sortMark(key) {
	if (sortKey.value !== key) return ""
	return sortAsc.value ? "↑" : "↓"
}

// The warning about leave that may be lost at year end only matters in the last quarter.
const showYearEndWarning = computed(() => new Date().getMonth() >= 9)

const totals = computed(() =>
	data.value.leave_types.map((leaveType) => {
		const values = rows.value.map((r) => r.leave[leaveType]).filter(Boolean)
		return {
			leave_type: leaveType,
			left: values.reduce((sum, v) => sum + Number(v.left || 0), 0),
			many_left: values.filter((v) => Number(v.left || 0) > MANY_DAYS_LEFT).length,
		}
	})
)

const noRecentLeave = computed(() => {
	const cutoff = new Date()
	cutoff.setMonth(cutoff.getMonth() - NO_LEAVE_MONTHS)
	const limit = cutoff.toISOString().slice(0, 10)
	return rows.value.filter((r) => !r.last_leave || r.last_leave < limit).length
})

/** "05-17" → day and month in the site's date order (17.05.), never a year (#1833, Decision 4). */
function formatBirthday(value) {
	if (!value) return "—"
	const [month, day] = value.split("-")
	const format = getDateFormat().toLowerCase()
	const separator = format.match(/[^a-z]/)?.[0] || "."
	return format.indexOf("mm") < format.indexOf("dd")
		? `${month}${separator}${day}`
		: `${day}${separator}${month}${separator === "." ? "." : ""}`
}

async function load() {
	loading.value = true
	try {
		data.value = await call(`${API}.get_employees`, { status: status.value, company: company.value || null })
		loadError.value = ""
	} catch (e) {
		loadError.value = errorMessage(e, "Could not load employees")
	} finally {
		loading.value = false
		loaded.value = true
	}
}

watch([status, company], load)

// "/" focuses the search, unless the user is typing somewhere.
function onKeydown(event) {
	const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(event.target?.tagName) || event.target?.isContentEditable
	if (typing || event.metaKey || event.ctrlKey || event.altKey) return
	if (event.key === "/") {
		event.preventDefault()
		searchEl.value?.$el?.querySelector("input")?.focus()
	}
}

onMounted(() => {
	window.addEventListener("keydown", onKeydown)
	load()
})
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown))
</script>
