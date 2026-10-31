<template>
	<section :id="`day-${date}`" class="flex gap-4 border-b border-outline-gray-2" :class="compact ? 'py-1' : ''">
		<!-- Date column: stays at the top while the day scrolls by -->
		<aside
			class="sticky top-0 z-[1] w-36 flex-none self-start pr-1 transition-all"
			:class="[compact ? 'py-0.5' : 'py-3', isToday ? 'text-ink-blue-3' : active ? 'text-ink-gray-9' : 'text-ink-gray-6']"
		>
			<div class="font-semibold leading-tight transition-all" :class="active || isToday ? 'text-xl' : 'text-sm'">
				{{ weekday }}
			</div>
			<div class="transition-all" :class="active || isToday ? 'text-sm' : 'text-xs'">{{ formatDate(date) }}</div>
			<span v-if="isToday" class="mt-1 inline-block rounded bg-surface-blue-2 px-1.5 py-0.5 text-xs font-medium text-ink-blue-3">{{ __("Today") }}</span>
			<div v-if="summary && !compact" class="mt-1 text-xs text-ink-gray-5">{{ summary }}</div>
		</aside>

		<p v-if="compact" class="py-0.5 text-xs text-ink-gray-5">{{ summary }}</p>
		<div v-else class="min-w-0 flex-1 space-y-3 py-3" :class="isToday ? 'rounded-lg' : ''">
			<!-- Plan card -->
			<DayPlanner v-if="isToday || plannerOpen" :date="isToday ? '' : date" @open-date="emit('open-date', $event)" @changed="emit('changed')" />
			<button
				v-else-if="isFuture"
				type="button"
				class="w-full rounded-lg border border-dashed border-outline-gray-3 px-4 py-2 text-left text-sm text-ink-gray-6 hover:bg-surface-gray-2"
				@click="plannerOpen = true"
			>
				{{ day.plan ? (planCount === 1 ? __("Planned: 1 ToDo. Open the plan") : __("Planned: {0} ToDos. Open the plan", [planCount])) : __("Plan this day") }}
			</button>
			<div v-else-if="day.plan" class="rounded-lg border border-outline-gray-2 bg-surface-white px-4 py-3 text-sm">
				<div class="text-ink-gray-8">{{ journalText }}</div>
				<p v-if="day.plan.reflection" class="mt-1 italic text-ink-gray-6">“{{ day.plan.reflection }}”</p>
				<p v-if="day.plan.status !== 'Closed'" class="mt-1 text-xs text-ink-gray-5">{{ __("This day was never shut down.") }}</p>
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
						<span>· {{ __("{0} without entries", [formatGap(row.minutes)]) }} ·</span>
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
							<span v-if="block.height >= 34" class="block truncate">{{ block.kind === "break" ? __("Break") : block.log.goal }}</span>
						</button>
						<!-- check-ins and ToDos; a point pushed down for room keeps a tick at its exact time -->
						<span
							v-for="point in row.points.filter((p) => p.shifted)"
							:key="`tick-${point.id}`"
							class="absolute right-0 h-px w-2 bg-outline-gray-4"
							:style="{ top: `${point.exactTop}px` }"
						/>
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
							<span class="absolute -top-2.5 left-14 rounded bg-surface-red-2 px-1 text-[10px] text-ink-red-4">{{ __("now") }}</span>
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
								{{ minuteLabel(selected.start) }} – {{ selected.running ? __("now") : minuteLabel(selected.end) }}
								· {{ selected.kind === "break" ? __("break") : selected.log.activity_type || __("work") }}
								<template v-if="selected.kind !== 'break' && selected.log.docstatus === 1">· {{ __("{0} % billable", [selected.log.percent_billable]) }}</template>
								<template v-if="selected.log.docstatus === 0">· {{ __("running") }}</template>
							</div>
						</div>
						<button type="button" class="text-xs text-ink-gray-5 hover:underline" @click="openDesk(deskRecordUrl('Timesheet Record', selected.log.name))">
							{{ __("Desk") }} ↗
						</button>
					</div>
				</div>
			</div>
		</div>
	</section>
</template>

<script setup>
import { computed, ref } from "vue"
import { useRouter } from "vue-router"
import { openDesk } from "@spa/utils/appWindow.js"
import { formatDate, weekdayName } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"
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
	// The day at the top of the view while scrolling: its date is shown larger.
	active: { type: Boolean, default: false },
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
const weekday = computed(() => weekdayName(props.date, "long"))
const planCount = computed(() => {
	const c = props.day.plan?.counts || {}
	return (c.done || 0) + (c.moved || 0) + (c.dropped || 0) + (c.open || 0)
})
const journalText = computed(() => {
	const c = props.day.plan?.counts || {}
	const parts = [__("{0} done", [c.done || 0])]
	if (c.moved) parts.push(__("{0} moved", [c.moved]))
	if (c.dropped) parts.push(__("{0} dropped", [c.dropped]))
	if (c.open) parts.push(__("{0} left open", [c.open]))
	return __("Plan: {0}.", [parts.join(", ")])
})
const summary = computed(() => {
	const worked = props.events.filter((e) => e.kind === "work").reduce((sum, e) => sum + (e.end - e.start), 0)
	const done = props.events.filter((e) => e.type === "todo").length
	const parts = []
	if (worked) parts.push(__("{0} logged", [formatGap(worked)]))
	if (done) parts.push(done === 1 ? __("1 ToDo done") : __("{0} ToDos done", [done]))
	if (compact.value && !parts.length) return isFuture.value ? "" : __("nothing recorded")
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
	const what = block.kind === "break" ? __("Break") : block.log.goal
	return `${minuteLabel(block.start)}–${block.running ? __("now") : minuteLabel(block.end)} ${block.log.project_name}: ${what}`
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
