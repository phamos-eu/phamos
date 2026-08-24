<template>
	<div class="flex min-h-0 flex-1 flex-col overflow-y-auto">
		<div
			class="flex flex-shrink-0 items-center justify-between border-b border-gray-200 px-4 py-2 dark:border-gray-800"
		>
			<button
				type="button"
				class="rounded-md px-2 py-1 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
				@click="shiftMonth(-1)"
			>
				←
			</button>
			<div class="text-sm font-semibold text-gray-900 dark:text-gray-100">{{ monthLabel }}</div>
			<button
				type="button"
				class="rounded-md px-2 py-1 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
				@click="shiftMonth(1)"
			>
				→
			</button>
		</div>

		<div
			class="grid grid-cols-7 gap-px border-b border-gray-200 bg-gray-200 text-center dark:border-gray-800 dark:bg-gray-800"
		>
			<div
				v-for="d in weekdays"
				:key="d"
				class="bg-gray-50 px-1 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:bg-gray-900 dark:text-gray-400"
			>
				{{ d }}
			</div>
		</div>

		<div class="grid flex-1 grid-cols-7 gap-px bg-gray-200 dark:bg-gray-800">
			<div
				v-for="(cell, idx) in cells"
				:key="idx"
				class="min-h-[72px] bg-white p-1 dark:bg-gray-900"
				:class="{ 'bg-gray-50 dark:bg-gray-950': !cell.inMonth }"
			>
				<div
					class="mb-1 text-[11px]"
					:class="
						cell.inMonth
							? 'font-medium text-gray-700 dark:text-gray-300'
							: 'text-gray-400 dark:text-gray-600'
					"
				>
					{{ cell.day }}
				</div>
				<button
					v-for="issue in cell.issues"
					:key="issue.name"
					type="button"
					class="mb-0.5 block w-full truncate rounded px-1 py-0.5 text-left text-[10px] hover:bg-gray-100 dark:hover:bg-gray-800"
					:class="
						issue.name === selectedName
							? 'bg-gray-900 text-white hover:bg-gray-800 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-gray-200'
							: 'bg-blue-50 text-blue-800 dark:bg-blue-950 dark:text-blue-300'
					"
					:title="issue.subject"
					@click="emit('select', issue.name)"
				>
					{{ issue.subject }}
				</button>
			</div>
		</div>

		<div v-if="noDateIssues.length" class="border-t border-gray-200 px-4 py-3 dark:border-gray-800">
			<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
				No date
			</div>
			<div class="flex flex-wrap gap-2">
				<button
					v-for="issue in noDateIssues"
					:key="issue.name"
					type="button"
					class="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
					:class="{
						'border-gray-900 bg-gray-50 dark:border-gray-300 dark:bg-gray-800': issue.name === selectedName,
					}"
					@click="emit('select', issue.name)"
				>
					{{ issue.name }} — {{ issue.subject }}
				</button>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, ref } from "vue"
import { formatMonthYear, getFirstDayOfWeekIndex, getWeekdayLabels } from "../utils/datetime"

const props = defineProps({
	issues: { type: Array, default: () => [] },
	selectedName: { type: String, default: null },
})

const emit = defineEmits(["select"])

const weekdays = computed(() => getWeekdayLabels())
const cursor = ref(startOfMonth(new Date()))

const monthLabel = computed(() => formatMonthYear(cursor.value))

function startOfMonth(d) {
	return new Date(d.getFullYear(), d.getMonth(), 1)
}

function parseIssueDate(issue) {
	const raw = issue.opening_date || (issue.creation ? String(issue.creation).slice(0, 10) : null)
	if (!raw) return null
	const m = String(raw).match(/^(\d{4})-(\d{2})-(\d{2})/)
	if (!m) return null
	const y = Number(m[1])
	const mo = Number(m[2]) - 1
	const day = Number(m[3])
	const d = new Date(y, mo, day)
	if (Number.isNaN(d.getTime())) return null
	return d
}

function dateKey(d) {
	const y = d.getFullYear()
	const m = String(d.getMonth() + 1).padStart(2, "0")
	const day = String(d.getDate()).padStart(2, "0")
	return `${y}-${m}-${day}`
}

const dated = computed(() => {
	const map = {}
	const undated = []
	for (const issue of props.issues) {
		const d = parseIssueDate(issue)
		if (!d) {
			undated.push(issue)
			continue
		}
		const key = dateKey(d)
		if (!map[key]) map[key] = []
		map[key].push(issue)
	}
	return { map, undated }
})

const noDateIssues = computed(() => dated.value.undated)

const cells = computed(() => {
	const year = cursor.value.getFullYear()
	const month = cursor.value.getMonth()
	const first = new Date(year, month, 1)
	const weekStart = getFirstDayOfWeekIndex()
	const startPad = (first.getDay() - weekStart + 7) % 7
	const daysInMonth = new Date(year, month + 1, 0).getDate()
	const prevDays = new Date(year, month, 0).getDate()
	const total = Math.ceil((startPad + daysInMonth) / 7) * 7
	const out = []
	for (let i = 0; i < total; i++) {
		let day
		let inMonth
		let cellDate
		if (i < startPad) {
			day = prevDays - startPad + i + 1
			inMonth = false
			cellDate = new Date(year, month - 1, day)
		} else if (i >= startPad + daysInMonth) {
			day = i - (startPad + daysInMonth) + 1
			inMonth = false
			cellDate = new Date(year, month + 1, day)
		} else {
			day = i - startPad + 1
			inMonth = true
			cellDate = new Date(year, month, day)
		}
		out.push({
			day,
			inMonth,
			issues: dated.value.map[dateKey(cellDate)] || [],
		})
	}
	return out
})

function shiftMonth(delta) {
	const d = cursor.value
	cursor.value = new Date(d.getFullYear(), d.getMonth() + delta, 1)
}
</script>
