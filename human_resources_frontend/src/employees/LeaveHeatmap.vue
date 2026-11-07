<template>
	<!--
		One row per month, one cell per day of the year, so a block of leave shows as a run of
		filled cells (#1836). One hue only: approved leave is filled, a request is outlined,
		weekends and holidays are muted. The type and status sit in each cell's tooltip, and
		the applications list below the chart names them, so colour never carries identity alone.
	-->
	<div class="select-none">
		<div class="grid gap-y-1" :style="{ gridTemplateColumns: `2.25rem repeat(31, minmax(0, 1fr))` }" role="img" :aria-label="`Leave days in ${year}`">
			<template v-for="month in months" :key="month.index">
				<div class="pr-2 text-right text-xs leading-4 text-ink-gray-5">{{ month.label }}</div>
				<div
					v-for="cell in month.cells"
					:key="cell.key"
					:class="['h-4 rounded-sm', cell.classes]"
					:title="cell.title"
				/>
			</template>
		</div>
		<div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-gray-6">
			<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm bg-surface-blue-3" /> Approved</span>
			<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm border-2 border-outline-blue-1 bg-surface-blue-1" /> Requested</span>
			<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm bg-surface-gray-2" /> Working day</span>
			<span class="inline-flex items-center gap-1.5"><span class="h-3 w-3 rounded-sm border border-outline-gray-2" /> Weekend or holiday</span>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { formatDate } from "@spa/contracts/contractFormat.js"

const props = defineProps({
	year: { type: Number, required: true },
	/** Leave applications with from_date, to_date, leave_type, status, half_day (sick leave never included). */
	applications: { type: Array, default: () => [] },
	/** { date, description, weekly_off } from the employee's holiday list. */
	holidays: { type: Array, default: () => [] },
})

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

const holidayByDate = computed(() => Object.fromEntries(props.holidays.map((h) => [String(h.date).slice(0, 10), h])))

// Every day covered by an application; a rejected one is left out, it never became an absence.
const leaveByDate = computed(() => {
	const map = {}
	for (const app of props.applications) {
		if (app.status === "Rejected") continue
		for (let d = new Date(app.from_date); d <= new Date(app.to_date); d.setDate(d.getDate() + 1)) {
			map[d.toISOString().slice(0, 10)] = app
		}
	}
	return map
})

function iso(year, month, day) {
	return `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`
}

const months = computed(() =>
	MONTHS.map((label, index) => {
		const days = new Date(props.year, index + 1, 0).getDate()
		const cells = []
		for (let day = 1; day <= 31; day++) {
			if (day > days) {
				cells.push({ key: `${index}-${day}`, classes: "", title: "" })
				continue
			}
			const date = iso(props.year, index, day)
			const leave = leaveByDate.value[date]
			const holiday = holidayByDate.value[date]
			const weekend = [0, 6].includes(new Date(props.year, index, day).getDay())
			const label = formatDate(date)
			if (leave) {
				const requested = leave.status !== "Approved"
				cells.push({
					key: date,
					classes: requested ? "border-2 border-outline-blue-1 bg-surface-blue-1" : "bg-surface-blue-3",
					title: `${label} · ${leave.leave_type} · ${requested ? "Requested" : "Approved"}`,
				})
			} else if (holiday || weekend) {
				// Recessive: an empty box, so the working-day grid and the leave blocks stand out.
				cells.push({
					key: date,
					classes: "border border-outline-gray-2",
					title: holiday && !holiday.weekly_off ? `${label} · ${holiday.description}` : label,
				})
			} else {
				cells.push({ key: date, classes: "bg-surface-gray-2", title: label })
			}
		}
		return { index, label, cells }
	})
)
</script>
