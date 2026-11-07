<template>
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-3 sm:p-5">
		<div class="flex w-full flex-col gap-5">
			<div v-if="loadError" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ loadError }}
			</div>
			<div v-else-if="loading && !loaded" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
				Loading employees…
			</div>
			<template v-else>
				<!-- Averages per employee, per leave type; never added up across types (#1833, Decision 6). -->
				<Sensitive tag="section" class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
					<StatCard
						v-for="avg in averages"
						:key="avg.leave_type"
						:label="`Ø ${avg.leave_type} left`"
						:value="avg.people ? formatNumber(avg.left) : '—'"
						:hint="avg.people ? `Ø ${formatNumber(avg.taken)} of ${formatNumber(avg.allocated)} taken · ${avg.people} ${avg.people === 1 ? 'employee' : 'employees'}` : 'No allocation'"
					/>
					<StatCard label="Ø years in company" :value="formatNumber(averageYears)" :hint="`${rows.length} ${rows.length === 1 ? 'employee' : 'employees'} in the list`" />
					<StatCard
						v-if="data.can_see_sick_days"
						label="Ø sick days this year"
						:value="data.sick_types_configured ? formatNumber(averageSickDays) : '—'"
						:hint="data.sick_types_configured ? 'Approved sick leave, HR Manager only' : 'Choose the sick leave types in phamos Settings'"
					/>
				</Sensitive>

				<!-- Who needs attention. A card is a filter: click it to see only those employees, click again to clear.
				     Blurred and inert in privacy mode (#1839): a filter would name the employees behind a count. -->
				<Sensitive tag="section" class="flex flex-wrap gap-2">
					<button
						v-for="card in attentionCards"
						:key="card.key"
						type="button"
						:aria-pressed="quickFilter === card.key"
						:class="[
							'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3',
							quickFilter === card.key
								? 'border-outline-gray-4 bg-surface-gray-7 text-ink-white'
								: card.count
									? 'border-outline-gray-2 bg-surface-white text-ink-gray-8 hover:bg-surface-gray-2'
									: 'border-outline-gray-1 bg-surface-white text-ink-gray-5 hover:bg-surface-gray-2',
						]"
						:title="card.title"
						@click="toggleQuickFilter(card.key)"
					>
						<span class="font-semibold tabular-nums" :class="card.count && quickFilter !== card.key ? 'text-ink-amber-3' : ''">{{ card.count }}</span>
						<span>{{ card.label }}</span>
					</button>
				</Sensitive>

				<section class="rounded-lg border border-outline-gray-2 bg-surface-white">
					<div class="flex flex-wrap items-center gap-3 border-b border-outline-gray-2 px-4 py-3">
						<FormControl
							ref="searchEl"
							v-model="search"
							type="text"
							size="sm"
							placeholder="Search employee…  /"
							class="w-56"
						/>
						<FormControl v-model="status" type="select" size="sm" :options="statusOptions" class="w-32" />
						<FormControl
							v-if="data.companies.length > 1"
							v-model="company"
							type="select"
							size="sm"
							:options="companyOptions"
							class="w-48"
						/>
						<span class="text-xs text-ink-gray-5">{{ rows.length }} {{ rows.length === 1 ? "employee" : "employees" }}</span>
						<button
							v-if="quickFilter"
							type="button"
							class="inline-flex items-center gap-1 rounded-full bg-surface-gray-2 px-2.5 py-1 text-xs text-ink-gray-7 hover:bg-surface-gray-3"
							@click="quickFilter = null"
						>
							{{ attentionCards.find((c) => c.key === quickFilter)?.label }}
							<FeatherIcon name="x" class="h-3 w-3" />
						</button>
					</div>

					<div class="overflow-x-auto">
						<table class="w-full border-separate border-spacing-0 text-sm">
							<thead class="text-xs text-ink-gray-5">
								<tr>
									<th :class="[stickyCell, headCell, 'text-left']" :aria-sort="ariaSort('employee_name')">
										<button type="button" :class="sortButton" @click="sortBy('employee_name')">
											Employee <SortMark :active="sortKey === 'employee_name'" :asc="sortAsc" />
										</button>
									</th>
									<th :class="[headCell, 'text-right']" :aria-sort="ariaSort('years_in_company')">
										<button type="button" :class="sortButton" @click="sortBy('years_in_company')">
											Years <SortMark :active="sortKey === 'years_in_company'" :asc="sortAsc" />
										</button>
									</th>
									<th :class="[headCell, 'text-left']" :aria-sort="ariaSort('birthday_in')">
										<button type="button" :class="sortButton" @click="sortBy('birthday_in')">
											Birthday <SortMark :active="sortKey === 'birthday_in'" :asc="sortAsc" />
										</button>
									</th>
									<th
										v-for="leaveType in data.leave_types"
										:key="leaveType"
										:class="[headCell, groupCell, 'text-right']"
										:aria-sort="ariaSort(`left:${leaveType}`)"
										:title="`${leaveType}: days left, and taken of allocated this year`"
									>
										<button type="button" :class="sortButton" @click="sortBy(`left:${leaveType}`)">
											{{ leaveType }} <SortMark :active="sortKey === `left:${leaveType}`" :asc="sortAsc" />
										</button>
									</th>
									<th :class="[headCell, groupCell, 'text-left']" :aria-sort="ariaSort('last_leave')">
										<button type="button" :class="sortButton" @click="sortBy('last_leave')">
											Last leave <SortMark :active="sortKey === 'last_leave'" :asc="sortAsc" />
										</button>
									</th>
									<th :class="[headCell, 'text-left']" :aria-sort="ariaSort('next_leave')">
										<button type="button" :class="sortButton" @click="sortBy('next_leave')">
											Next leave <SortMark :active="sortKey === 'next_leave'" :asc="sortAsc" />
										</button>
									</th>
									<th :class="[headCell, 'text-right']" :aria-sort="ariaSort('pending_count')" title="Leave applications waiting for a decision">
										<button type="button" :class="sortButton" @click="sortBy('pending_count')">
											Waiting <SortMark :active="sortKey === 'pending_count'" :asc="sortAsc" />
										</button>
									</th>
									<th
										v-if="data.can_see_sick_days"
										:class="[headCell, groupCell, 'text-right']"
										:aria-sort="ariaSort('sick_days')"
										title="Approved sick days this year. Only HR Manager sees this column."
									>
										<button type="button" :class="sortButton" @click="sortBy('sick_days')">
											Sick days <SortMark :active="sortKey === 'sick_days'" :asc="sortAsc" />
										</button>
									</th>
									<template v-if="data.can_see_contracts">
										<th :class="[headCell, groupCell, 'text-right']" :aria-sort="ariaSort('fte_percentage')">
											<button type="button" :class="sortButton" @click="sortBy('fte_percentage')">
												FTE <SortMark :active="sortKey === 'fte_percentage'" :asc="sortAsc" />
											</button>
										</th>
										<th :class="[headCell, 'text-left']" :aria-sort="ariaSort('contract_end')">
											<button type="button" :class="sortButton" @click="sortBy('contract_end')">
												Contract end <SortMark :active="sortKey === 'contract_end'" :asc="sortAsc" />
											</button>
										</th>
									</template>
								</tr>
							</thead>
							<tbody>
								<!-- A row opens the employee dialog (#1836); Enter does the same from the keyboard. -->
								<tr
									v-for="row in sortedRows"
									:key="row.employee"
									class="group cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-3"
									tabindex="0"
									role="button"
									:aria-label="`Details of ${row.employee_name}`"
									@click="openEmployee(row, $event)"
									@keydown.enter.prevent="openEmployee(row, $event)"
								>
									<td :class="[stickyCell, bodyCell]">
										<div class="truncate font-medium text-ink-gray-9">{{ row.employee_name }}</div>
										<div class="truncate text-xs text-ink-gray-5">
											{{ [row.department, row.designation].filter(Boolean).join(" · ") || row.employee }}
										</div>
									</td>
									<td :class="[bodyCell, 'text-right tabular-nums text-ink-gray-8']">{{ formatNumber(row.years_in_company) }}</td>
									<td :class="[bodyCell, 'tabular-nums']">
										<Empty v-if="!row.birthday" />
										<template v-else>
											<span class="text-ink-gray-8">{{ formatBirthday(row.birthday) }}</span>
											<span v-if="row.birthday_in <= BIRTHDAY_DAYS" class="ml-2 text-xs text-ink-amber-3">{{ birthdayHint(row.birthday) }}</span>
										</template>
									</td>
									<td v-for="leaveType in data.leave_types" :key="leaveType" :class="[bodyCell, groupCell, 'text-right tabular-nums']">
										<Empty v-if="!row.leave[leaveType]" />
										<Sensitive v-else tag="div">
											<div class="font-medium text-ink-gray-9">{{ formatNumber(row.leave[leaveType].left) }}</div>
											<div class="text-xs text-ink-gray-5">
												{{ formatNumber(row.leave[leaveType].taken) }} of {{ formatNumber(row.leave[leaveType].allocated) }} taken
											</div>
										</Sensitive>
									</td>
									<td :class="[bodyCell, groupCell, 'tabular-nums text-ink-gray-8']">
										<Empty v-if="!row.last_leave" />
										<Sensitive v-else>{{ formatDate(row.last_leave) }}</Sensitive>
									</td>
									<td :class="[bodyCell, 'tabular-nums text-ink-gray-8']">
										<Empty v-if="!row.next_leave" />
										<Sensitive v-else>{{ formatDate(row.next_leave) }}</Sensitive>
									</td>
									<td :class="[bodyCell, 'text-right tabular-nums']">
										<Empty v-if="!row.pending_count" />
										<Sensitive v-else class="font-medium text-ink-amber-3">{{ row.pending_count }}</Sensitive>
									</td>
									<td v-if="data.can_see_sick_days" :class="[bodyCell, groupCell, 'text-right tabular-nums text-ink-gray-8']">
										<Empty v-if="!data.sick_types_configured" title="Choose the sick leave types in phamos Settings → Human Resources Cockpit" />
										<Empty v-else-if="!row.sick_days" />
										<Sensitive v-else>{{ formatNumber(row.sick_days) }}</Sensitive>
									</td>
									<template v-if="data.can_see_contracts">
										<td :class="[bodyCell, groupCell, 'text-right tabular-nums text-ink-gray-8']">
											<Empty v-if="row.fte_percentage == null" title="No contract in force" />
											<Sensitive v-else>{{ formatPercent(row.fte_percentage) }}</Sensitive>
										</td>
										<td :class="[bodyCell, 'tabular-nums text-ink-gray-8']">
											<Empty v-if="row.fte_percentage == null" />
											<Sensitive v-else-if="!row.contract_end" class="text-ink-gray-5">open-ended</Sensitive>
											<Sensitive v-else>{{ formatDate(row.contract_end) }}</Sensitive>
										</td>
									</template>
								</tr>
							</tbody>
						</table>
						<div v-if="!sortedRows.length" class="py-16 text-center">
							<p class="font-medium text-ink-gray-9">No employees found</p>
							<p class="mt-1 text-sm text-ink-gray-6">Clear the search or choose another status.</p>
						</div>
					</div>
					<p v-if="!data.leave_types.length && sortedRows.length" class="border-t border-outline-gray-1 px-4 py-3 text-xs text-ink-gray-5">
						No leave is allocated this year, so there are no leave columns yet. Leave Allocations come from HRMS.
					</p>
				</section>
			</template>
		</div>

		<EmployeeDialog
			v-model="dialogOpen"
			:employee="dialogEmployee"
			:employee-name="dialogEmployeeName"
			@update:model-value="(open) => !open && focusRow()"
		/>
	</div>
</template>

<script setup>
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { call } from "frappe-ui"
import StatCard from "@spa/components/dashboard/StatCard.vue"
import Sensitive from "@spa/components/Sensitive.vue"
import { usePrivacyMode } from "@spa/composables/usePrivacyMode.js"
import EmployeeDialog from "./EmployeeDialog.vue"
import { errorMessage, formatDate, formatNumber, formatPercent } from "@spa/contracts/contractFormat.js"
import { getDateFormat } from "@spa/utils/datetime.js"

// Employees list with leave statistics (#1835). Sick days and contract figures come only for
// the roles allowed to see them (#1833, Decisions 2 and 4); the API leaves them out otherwise.
const API = "phamos.api.hr_employees"
const MANY_DAYS_LEFT = 10
const NO_LEAVE_MONTHS = 2
const BIRTHDAY_DAYS = 30

const headCell = "border-b border-outline-gray-2 px-3 py-2 font-medium whitespace-nowrap"
const bodyCell = "border-b border-outline-gray-1 px-3 py-2.5 whitespace-nowrap align-top group-hover:bg-surface-gray-1"
const groupCell = "border-l border-outline-gray-1"
const stickyCell = "sticky left-0 z-[1] min-w-56 max-w-72 bg-surface-white"
const sortButton = "inline-flex items-center gap-1 rounded hover:text-ink-gray-8 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"

// A muted dash for "nothing here", so empty cells don't compete with the numbers.
const Empty = (props) => h("span", { class: "text-ink-gray-4", title: props.title }, "—")
Empty.props = { title: { type: String, default: "" } }
const SortMark = (props) => (props.active ? h("span", { "aria-hidden": "true" }, props.asc ? "↑" : "↓") : null)
SortMark.props = { active: Boolean, asc: Boolean }

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
const quickFilter = ref(null)
// An active card filter shows which employees are behind a count; it ends when data hides (#1839).
const { hidden: privacyHidden } = usePrivacyMode()
watch(privacyHidden, (hidden) => {
	if (hidden) quickFilter.value = null
})
const dialogOpen = ref(false)
const dialogEmployee = ref("")
const dialogEmployeeName = ref("")
let lastRow = null

function openEmployee(row, event) {
	lastRow = event?.currentTarget || null
	dialogEmployee.value = row.employee
	dialogEmployeeName.value = row.employee_name
	dialogOpen.value = true
}

// Back to the row the dialog came from, so keyboard users don't lose their place. The
// dialog's own focus handling runs after its leave transition, so this waits for that.
function focusRow() {
	setTimeout(() => lastRow?.focus?.(), 300)
}

const statusOptions = [
	{ label: "Active", value: "Active" },
	{ label: "Left", value: "Left" },
	{ label: "All", value: "All" },
]
const companyOptions = computed(() => [
	{ label: "All companies", value: "" },
	...data.value.companies.map((c) => ({ label: c, value: c })),
])

/** Days until the next birthday (0 = today), from "MM-DD"; null without a date. */
function daysToBirthday(value) {
	if (!value) return null
	const [month, day] = value.split("-").map(Number)
	const today = new Date()
	today.setHours(0, 0, 0, 0)
	let next = new Date(today.getFullYear(), month - 1, day)
	if (next < today) next = new Date(today.getFullYear() + 1, month - 1, day)
	return Math.round((next - today) / 86400000)
}

const employees = computed(() =>
	data.value.employees.map((row) => ({ ...row, birthday_in: daysToBirthday(row.birthday) }))
)

const searched = computed(() => {
	const q = search.value.trim().toLowerCase()
	if (!q) return employees.value
	return employees.value.filter((row) =>
		[row.employee_name, row.employee, row.department, row.designation].some((v) =>
			String(v || "").toLowerCase().includes(q)
		)
	)
})

const rows = computed(() => {
	const active = quickFilters.value.find((f) => f.key === quickFilter.value)
	return active ? searched.value.filter(active.test) : searched.value
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

function ariaSort(key) {
	if (sortKey.value !== key) return "none"
	return sortAsc.value ? "ascending" : "descending"
}

// Averages are over the employees in the list (search and quick filter applied), per leave type.
function average(values) {
	return values.length ? values.reduce((sum, v) => sum + v, 0) / values.length : 0
}

const averages = computed(() =>
	data.value.leave_types.map((leaveType) => {
		const values = rows.value.map((r) => r.leave[leaveType]).filter(Boolean)
		return {
			leave_type: leaveType,
			people: values.length,
			left: average(values.map((v) => Number(v.left || 0))),
			taken: average(values.map((v) => Number(v.taken || 0))),
			allocated: average(values.map((v) => Number(v.allocated || 0))),
		}
	})
)
const averageYears = computed(() =>
	average(rows.value.filter((r) => r.years_in_company != null).map((r) => Number(r.years_in_company)))
)
const averageSickDays = computed(() => average(rows.value.map((r) => Number(r.sick_days || 0))))

// Quick filters behind the attention cards. Each one is a predicate on a row; the counts come
// from the search result, so a card still tells the whole picture while another card is active.
const noLeaveLimit = computed(() => {
	const cutoff = new Date()
	cutoff.setMonth(cutoff.getMonth() - NO_LEAVE_MONTHS)
	// Local date, not toISOString(): that is UTC and shifts the day just after midnight in Europe.
	const pad = (n) => String(n).padStart(2, "0")
	return `${cutoff.getFullYear()}-${pad(cutoff.getMonth() + 1)}-${pad(cutoff.getDate())}`
})
const quickFilters = computed(() => {
	const limit = noLeaveLimit.value
	const filters = [
		{
			key: "no_recent_leave",
			label: `no leave since ${NO_LEAVE_MONTHS} months`,
			title: "No approved leave in that time; sick leave does not count",
			test: (r) => !r.last_leave || r.last_leave < limit,
		},
		{
			key: "many_left",
			label: `more than ${MANY_DAYS_LEFT} days left`,
			title: "Leave of any type that may be lost at year end",
			test: (r) => Object.values(r.leave).some((v) => Number(v.left || 0) > MANY_DAYS_LEFT),
		},
		{
			key: "pending",
			label: "requests waiting",
			title: "Leave applications not yet decided",
			test: (r) => Number(r.pending_count || 0) > 0,
		},
		{
			key: "birthday",
			label: `birthdays in ${BIRTHDAY_DAYS} days`,
			title: "Day and month only",
			test: (r) => r.birthday_in !== null && r.birthday_in <= BIRTHDAY_DAYS,
		},
	]
	if (data.value.can_see_sick_days && data.value.sick_types_configured) {
		filters.push({
			key: "sick_above_average",
			label: "sick days above average",
			title: "More approved sick days this year than the average of the list",
			test: (r) => Number(r.sick_days || 0) > averageSickDays.value && Number(r.sick_days || 0) > 0,
		})
	}
	return filters
})
const attentionCards = computed(() =>
	quickFilters.value.map((f) => ({ ...f, count: searched.value.filter(f.test).length }))
)

function toggleQuickFilter(key) {
	quickFilter.value = quickFilter.value === key ? null : key
}

/** "05-17" → day and month in the site's date order (17.05.), never a year (#1833, Decision 4). */
function formatBirthday(value) {
	const [month, day] = value.split("-")
	const format = getDateFormat().toLowerCase()
	const separator = format.match(/[^a-z]/)?.[0] || "."
	return format.indexOf("mm") < format.indexOf("dd")
		? `${month}${separator}${day}`
		: `${day}${separator}${month}${separator === "." ? "." : ""}`
}

function birthdayHint(value) {
	const days = daysToBirthday(value)
	if (days === 0) return "today"
	if (days === 1) return "tomorrow"
	return `in ${days} days`
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

// "/" focuses the search; Escape in the search clears it.
function onKeydown(event) {
	const input = searchEl.value?.$el?.querySelector("input")
	if (event.key === "Escape" && event.target === input && search.value) {
		search.value = ""
		return
	}
	const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(event.target?.tagName) || event.target?.isContentEditable
	if (typing || event.metaKey || event.ctrlKey || event.altKey) return
	if (event.key === "/") {
		event.preventDefault()
		input?.focus()
	}
}

onMounted(() => {
	window.addEventListener("keydown", onKeydown)
	load()
})
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown))
</script>
