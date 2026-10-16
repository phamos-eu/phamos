<template>
	<section :id="`day-${date}`" class="scroll-mt-0">
		<!-- Sticky day header -->
		<header
			class="sticky top-0 z-[1] -mx-5 flex items-center justify-between border-b border-outline-gray-2 bg-surface-gray-1 px-5 py-2"
			:class="compact ? 'py-1' : ''"
		>
			<h2 class="text-sm font-semibold" :class="isToday ? 'text-ink-gray-9' : 'text-ink-gray-7'">
				{{ title }}
				<span v-if="isToday" class="ml-2 rounded bg-surface-gray-7 px-1.5 py-0.5 text-xs font-medium text-ink-white">Today</span>
			</h2>
			<span v-if="summary" class="text-xs text-ink-gray-5">{{ summary }}</span>
		</header>

		<div v-if="!compact" class="space-y-3 py-3">
			<!-- Plan card -->
			<DayPlanner v-if="isToday || plannerOpen" :date="isToday ? '' : date" @open-date="emit('open-date', $event)" @changed="emit('changed')" />
			<button
				v-else-if="isFuture"
				type="button"
				class="w-full rounded-lg border border-dashed border-outline-gray-3 px-4 py-2 text-left text-sm text-ink-gray-6 hover:bg-surface-gray-2"
				@click="plannerOpen = true"
			>
				{{ day.plan ? `Planned: ${planCount} ToDos. Open the plan` : "Plan this day" }}
			</button>
			<div v-else-if="day.plan" class="rounded-lg border border-outline-gray-2 bg-surface-white px-4 py-3 text-sm">
				<div class="text-ink-gray-8">{{ journalText }}</div>
				<p v-if="day.plan.reflection" class="mt-1 italic text-ink-gray-6">“{{ day.plan.reflection }}”</p>
				<p v-if="day.plan.status !== 'Closed'" class="mt-1 text-xs text-ink-gray-5">This day was never shut down.</p>
			</div>

			<!-- Time axis -->
			<div v-if="layout.rows.length" class="rounded-lg border border-outline-gray-2 bg-surface-white">
				<template v-for="(row, index) in layout.rows" :key="index">
					<div
						v-if="row.kind === 'gap'"
						class="flex items-center gap-3 border-y border-dashed border-outline-gray-2 bg-surface-gray-1 px-3 text-xs text-ink-gray-5"
						:style="{ height: `${row.height}px` }"
					>
						<span class="w-12 tabular-nums">{{ minuteLabel(row.start) }}</span>
						<span>· {{ formatGap(row.minutes) }} without entries ·</span>
					</div>
					<div v-else class="relative" :style="{ height: `${row.height}px` }">
						<!-- hour ticks -->
						<div
							v-for="hour in row.hours"
							:key="hour.label"
							class="absolute inset-x-0 flex items-start border-t border-outline-gray-1"
							:style="{ top: `${hour.top}px` }"
						>
							<span class="w-14 -translate-y-2 bg-surface-white pl-3 text-xs tabular-nums text-ink-gray-4">{{ hour.label }}</span>
						</div>
						<!-- time log blocks -->
						<button
							v-for="block in row.blocks"
							:key="block.id"
							type="button"
							class="absolute flex flex-col justify-start overflow-hidden rounded border-l-4 px-2 pt-1 text-left text-xs"
							:class="blockClass(block)"
							:style="blockStyle(block, row.lanes)"
							:title="blockTitle(block)"
							@click="selected = selected?.id === block.id ? null : block"
						>
							<span v-if="block.height >= 18" class="block truncate font-medium">{{ block.log.project_name }}</span>
							<span v-if="block.height >= 34" class="block truncate">{{ block.kind === "break" ? "Break" : block.log.goal }}</span>
						</button>
						<!-- check-ins and ToDos -->
						<button
							v-for="point in row.points"
							:key="point.id"
							type="button"
							class="absolute right-3 flex max-w-[45%] -translate-y-1/2 items-center gap-1.5 rounded px-1.5 py-0.5 text-xs hover:bg-surface-gray-2"
							:style="{ top: `${point.top}px` }"
							:title="point.title"
							@click="openPoint(point)"
						>
							<FeatherIcon :name="point.icon" class="h-3.5 w-3.5 flex-none" :class="point.iconClass" />
							<span class="tabular-nums text-ink-gray-5">{{ minuteLabel(point.start) }}</span>
							<span class="truncate text-ink-gray-8">{{ point.label }}</span>
							<FeatherIcon v-if="point.important" name="star" class="h-3 w-3 flex-none text-ink-amber-3" />
						</button>
						<!-- now -->
						<div v-if="row.nowTop !== null" class="pointer-events-none absolute inset-x-0 border-t-2 border-ink-red-3" :style="{ top: `${row.nowTop}px` }">
							<span class="absolute -top-2.5 left-14 rounded bg-surface-red-2 px-1 text-[10px] text-ink-red-4">now</span>
						</div>
					</div>
				</template>
				<!-- details of the clicked time log -->
				<div v-if="selected" class="border-t border-outline-gray-2 px-4 py-3 text-sm">
					<div class="flex items-start justify-between gap-3">
						<div>
							<div class="font-medium text-ink-gray-9">{{ selected.log.project_name }}</div>
							<div class="text-ink-gray-7">{{ selected.log.goal }}</div>
							<div v-if="selected.log.result" class="mt-1 text-ink-gray-6">{{ selected.log.result }}</div>
							<div class="mt-1 text-xs text-ink-gray-5">
								{{ minuteLabel(selected.start) }} – {{ selected.running ? "now" : minuteLabel(selected.end) }}
								· {{ selected.kind === "break" ? "break" : selected.log.activity_type || "work" }}
								<template v-if="selected.kind !== 'break' && selected.log.docstatus === 1">· {{ selected.log.percent_billable }} % billable</template>
								<template v-if="selected.log.docstatus === 0">· running</template>
							</div>
						</div>
						<button type="button" class="text-xs text-ink-gray-5 hover:underline" @click="openDesk(deskRecordUrl('Timesheet Record', selected.log.name))">
							Desk ↗
						</button>
					</div>
				</div>
			</div>
			<p v-else-if="!isFuture && !isToday && !day.plan" class="text-xs text-ink-gray-5">Nothing recorded.</p>
		</div>
	</section>
</template>

<script setup>
import { computed, ref } from "vue"
import { useRouter } from "vue-router"
import { openDesk } from "@spa/utils/appWindow.js"
import { formatDate } from "@spa/utils/datetime.js"
import { deskRecordUrl } from "@spa/utils/deskUrl.js"
import { formatGap, layoutDay } from "@spa/utils/timelineLayout.js"
import DayPlanner from "./DayPlanner.vue"

const props = defineProps({
	date: { type: String, required: true },
	day: { type: Object, default: () => ({}) },
	// Events of this day in minutes: [{ id, kind: "point" | "work" | "break", start, end, ... }]
	events: { type: Array, default: () => [] },
	today: { type: String, required: true },
	nowMinute: { type: Number, default: null },
})
const emit = defineEmits(["open-date", "changed"])

const router = useRouter()
const plannerOpen = ref(false)
const selected = ref(null)

const isToday = computed(() => props.date === props.today)
const isFuture = computed(() => props.date > props.today)
// Past days with nothing at all, and future days without a plan, collapse to one line.
const compact = computed(() => !isToday.value && !isFuture.value && !props.events.length && !props.day.plan)
const layout = computed(() => (isFuture.value ? { rows: [] } : layoutDay(props.events, { now: isToday.value ? props.nowMinute : null })))
const title = computed(() => {
	const d = new Date(`${props.date}T12:00:00`)
	return `${d.toLocaleDateString([], { weekday: "long" })} ${formatDate(props.date)}`
})
const planCount = computed(() => {
	const c = props.day.plan?.counts || {}
	return (c.done || 0) + (c.moved || 0) + (c.dropped || 0) + (c.open || 0)
})
const journalText = computed(() => {
	const c = props.day.plan?.counts || {}
	const parts = [`${c.done || 0} done`]
	if (c.moved) parts.push(`${c.moved} moved`)
	if (c.dropped) parts.push(`${c.dropped} dropped`)
	if (c.open) parts.push(`${c.open} left open`)
	return `Plan: ${parts.join(", ")}.`
})
const summary = computed(() => {
	const worked = props.events.filter((e) => e.kind === "work").reduce((sum, e) => sum + (e.end - e.start), 0)
	const done = props.events.filter((e) => e.type === "todo").length
	const parts = []
	if (worked) parts.push(`${formatGap(worked)} logged`)
	if (done) parts.push(`${done} ToDo${done === 1 ? "" : "s"} done`)
	if (compact.value && !parts.length) return isFuture.value ? "" : "nothing recorded"
	return parts.join(" · ")
})

function minuteLabel(minute) {
	const m = Math.round(minute)
	return `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`
}

function blockClass(block) {
	if (block.kind === "break") return "timeline-break border-outline-gray-3 text-ink-gray-6"
	if (block.running) return "border-ink-green-3 bg-surface-green-2 text-ink-gray-9"
	return "border-ink-blue-3 bg-surface-blue-2 text-ink-gray-9"
}

function blockStyle(block, lanes) {
	const width = `calc((100% - 4.5rem - 45%) / ${lanes})`
	return { top: `${block.top}px`, height: `${block.height}px`, left: `calc(4rem + ${block.lane} * ${width})`, width }
}

function blockTitle(block) {
	const what = block.kind === "break" ? "Break" : block.log.goal
	return `${minuteLabel(block.start)}–${block.running ? "now" : minuteLabel(block.end)} ${block.log.project_name}: ${what}`
}

function openPoint(point) {
	if (point.type === "todo") router.push({ name: "TodoDetail", params: { name: point.name } })
	else openDesk(deskRecordUrl("Employee Checkin", point.name))
}
</script>

<style scoped>
.timeline-break {
	background: repeating-linear-gradient(135deg, var(--surface-gray-2) 0 6px, var(--surface-gray-1) 6px 12px);
}
</style>
