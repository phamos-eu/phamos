<template>
	<section v-if="startDate" class="space-y-2">
		<div class="flex items-center justify-between gap-2">
			<label class="block text-xs text-ink-gray-5">Schedule preview</label>
			<span class="text-[11px] text-ink-gray-5">
				{{ rangeLabel }}
			</span>
		</div>

		<div
			v-if="loading"
			class="flex h-28 items-center justify-center rounded-lg border border-outline-gray-2 bg-surface-gray-1 text-xs text-ink-gray-5"
		>
			Loading timeline…
		</div>
		<div
			v-else-if="loadError"
			class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-4 text-xs text-red-600 dark:text-red-400"
		>
			{{ loadError }}
		</div>
		<div
			v-else
			ref="scrollEl"
			class="overflow-x-auto rounded-lg border border-outline-gray-2 bg-surface-white"
		>
			<div class="relative" :style="{ width: `${timeline.totalWidth + LABEL_WIDTH}px`, minWidth: '100%' }">
				<!-- Header -->
				<div class="sticky top-0 z-[1] flex border-b border-outline-gray-2 bg-surface-gray-1">
					<div
						class="flex-shrink-0 border-r border-outline-gray-2 px-2 py-1 text-[10px] font-medium uppercase tracking-wide text-ink-gray-5"
						:style="{ width: `${LABEL_WIDTH}px` }"
					>
						Tasks
					</div>
					<div class="relative flex-1" :style="{ width: `${timeline.totalWidth}px` }">
						<div class="relative h-5 border-b border-outline-gray-1">
							<div
								v-for="month in timeline.months"
								:key="month.key"
								class="absolute top-0 flex h-5 items-center overflow-hidden border-r border-outline-gray-1 px-1 text-[10px] font-medium text-ink-gray-6"
								:style="{ left: `${month.left}px`, width: `${month.width}px` }"
							>
								{{ month.label }}
							</div>
						</div>
						<div class="relative h-5">
							<div
								v-for="day in timeline.days"
								:key="day.iso"
								class="absolute top-0 flex h-5 items-center justify-center border-r border-outline-gray-1 text-[10px] text-ink-gray-5"
								:class="{ 'bg-blue-50 font-semibold text-blue-700 dark:bg-blue-950/40 dark:text-blue-300': day.iso === todayIso }"
								:style="{ left: `${day.left}px`, width: `${day.width}px` }"
								:title="formatDate(day.iso)"
							>
								{{ day.date.getDate() }}
							</div>
						</div>
					</div>
				</div>

				<!-- Rows -->
				<div
					v-for="row in rows"
					:key="row.id"
					class="flex border-b border-outline-gray-1 last:border-b-0"
					:class="row.isDraft ? 'bg-blue-50/60 dark:bg-blue-950/20' : ''"
					:style="{ height: `${ROW_HEIGHT}px` }"
				>
					<div
						class="flex flex-shrink-0 items-center border-r border-outline-gray-2 px-2 text-xs"
						:style="{ width: `${LABEL_WIDTH}px` }"
						:title="row.name"
					>
						<span
							class="truncate"
							:class="row.isDraft ? 'font-semibold text-ink-gray-9' : 'text-ink-gray-7'"
						>
							{{ row.name }}
						</span>
					</div>
					<div class="relative flex-1" :style="{ width: `${timeline.totalWidth}px` }">
						<div
							v-if="todayStrip"
							class="pointer-events-none absolute inset-y-0 z-0 bg-blue-500/10"
							:style="{ left: `${todayStrip.left}px`, width: `${todayStrip.width}px` }"
						/>
						<div
							v-if="todayStrip"
							class="pointer-events-none absolute inset-y-0 z-0 w-px bg-blue-500"
							:style="{ left: `${todayStrip.edgeLeft}px` }"
						/>
						<div
							class="absolute top-1.5 flex h-5 items-center overflow-hidden rounded px-1.5 text-[10px] font-medium"
							:class="barClass(row)"
							:style="barStyle(row)"
							:title="barTitle(row)"
							:role="row.isDraft ? undefined : 'button'"
							:tabindex="row.isDraft ? undefined : 0"
							@click="onBarClick(row)"
							@keydown.enter.prevent="onBarClick(row)"
							@keydown.space.prevent="onBarClick(row)"
						>
							<span class="truncate">{{ row.name }}</span>
						</div>
					</div>
				</div>

				<div
					v-if="!rows.length"
					class="flex h-16 items-center justify-center text-xs text-ink-gray-5"
				>
					No overlapping tasks in this window
				</div>
			</div>
		</div>
		<p class="text-[11px] text-ink-gray-5">
			<span class="inline-block h-2 w-2 rounded-sm bg-blue-600 align-middle dark:bg-blue-500" />
			New task
			<span class="mx-1.5 text-ink-gray-4">·</span>
			Click a nearby task to depend on it
		</p>
	</section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue"
import { call, debounce } from "frappe-ui"
import { formatDate, todayIsoInUserTz } from "@spa/utils/datetime.js"
import {
	buildTimeline,
	expandFrameToTasks,
	normalizeFrameRange,
	scrollLeftForDate,
	todayStripRect,
} from "@spa/utils/ganttTimeline.js"
import { formatDateIso } from "@spa/utils/ganttTimelineFormat.js"
import spaConfig from "@/config"

const LABEL_WIDTH = 140
const ROW_HEIGHT = 32
const COLUMN_WIDTH = 22
const MAX_CONTEXT = 8
const PAD_BEFORE = 7
const PAD_AFTER = 14

const props = defineProps({
	startDate: { type: String, default: "" },
	endDate: { type: String, default: "" },
	subject: { type: String, default: "" },
	apiPrefix: { type: String, default: "" },
	linkedTaskIds: { type: Array, default: () => [] },
})

const emit = defineEmits(["select-task"])

const API = computed(() => props.apiPrefix || spaConfig.api)
const scrollEl = ref(null)
const loading = ref(false)
const loadError = ref("")
const contextTasks = ref([])

const linkedSet = computed(() => new Set((props.linkedTaskIds || []).map(String)))

const todayIso = computed(() => todayIsoInUserTz())

const draftEnd = computed(() => {
	const start = (props.startDate || "").trim()
	const end = (props.endDate || "").trim()
	if (!start) return ""
	if (end && end >= start) return end
	return start
})

const rangeLabel = computed(() => {
	if (!props.startDate) return ""
	const end = draftEnd.value
	if (!end || end === props.startDate) return formatDate(props.startDate)
	return `${formatDate(props.startDate)} – ${formatDate(end)}`
})

function parseDate(iso) {
	if (!iso) return null
	const d = new Date(`${String(iso).slice(0, 10)}T00:00:00`)
	return Number.isNaN(d.getTime()) ? null : d
}

function addDays(date, days) {
	const d = new Date(date)
	d.setDate(d.getDate() + days)
	return d
}

const frame = computed(() => {
	const start = parseDate(props.startDate)
	const end = parseDate(draftEnd.value)
	if (!start || !end) return null

	let frameStart = addDays(start, -PAD_BEFORE)
	let frameEnd = addDays(end, PAD_AFTER)

	const contextDates = contextTasks.value
		.filter((t) => t.exp_start_date)
		.flatMap((t) => {
			const s = parseDate(t.exp_start_date)
			const e = parseDate(t.exp_end_date || t.exp_start_date)
			return [s, e].filter(Boolean)
		})

	const expanded = expandFrameToTasks(contextDates, frameStart, frameEnd)
	return normalizeFrameRange(expanded.start, expanded.end)
})

const timeline = computed(() => {
	if (!frame.value) {
		return { days: [], months: [], weeks: [], totalWidth: 0, rangeStart: null, rangeEnd: null }
	}
	return buildTimeline(frame.value.start, frame.value.end, COLUMN_WIDTH, COLUMN_WIDTH)
})

const todayStrip = computed(() => todayStripRect(timeline.value))

function overlapsWindow(task, windowStart, windowEnd) {
	const start = parseDate(task.exp_start_date)
	if (!start) return false
	let end = parseDate(task.exp_end_date || task.exp_start_date) || start
	if (end < start) end = start
	return end >= windowStart && start <= windowEnd
}

function distanceToDraft(task, draftStart, draftEndDate) {
	const start = parseDate(task.exp_start_date)
	if (!start) return Number.POSITIVE_INFINITY
	let end = parseDate(task.exp_end_date || task.exp_start_date) || start
	if (end < start) end = start
	if (end < draftStart) return draftStart - end
	if (start > draftEndDate) return start - draftEndDate
	return 0
}

const rows = computed(() => {
	const start = parseDate(props.startDate)
	const end = parseDate(draftEnd.value)
	if (!start || !end || !frame.value) return []

	const draft = {
		id: "__draft__",
		name: (props.subject || "").trim() || "New task",
		start: formatDateIso(start),
		end: formatDateIso(end),
		isDraft: true,
	}

	const nearby = contextTasks.value
		.filter((t) => overlapsWindow(t, frame.value.start, frame.value.end))
		.map((t) => ({
			task: t,
			distance: distanceToDraft(t, start, end),
		}))
		.sort((a, b) => a.distance - b.distance || String(a.task.exp_start_date).localeCompare(String(b.task.exp_start_date)))
		.slice(0, MAX_CONTEXT)
		.map(({ task }) => {
			const s = parseDate(task.exp_start_date)
			let e = parseDate(task.exp_end_date || task.exp_start_date) || s
			if (e < s) e = s
			return {
				id: task.name,
				name: task.subject || task.name,
				start: formatDateIso(s),
				end: formatDateIso(e),
				isDraft: false,
				isLinked: linkedSet.value.has(String(task.name)),
			}
		})
		.sort((a, b) => a.start.localeCompare(b.start) || a.name.localeCompare(b.name))

	return [draft, ...nearby]
})

function barClass(row) {
	if (row.isDraft) {
		return "bg-blue-600 text-white shadow-sm dark:bg-blue-500"
	}
	if (row.isLinked) {
		return "cursor-pointer bg-emerald-600 text-white ring-2 ring-emerald-300 dark:bg-emerald-500 dark:ring-emerald-700"
	}
	return "cursor-pointer bg-surface-gray-4 text-ink-gray-8 hover:bg-surface-gray-5 dark:bg-gray-700 dark:text-gray-100 dark:hover:bg-gray-600"
}

function barTitle(row) {
	const range = `${formatDate(row.start)} – ${formatDate(row.end)}`
	if (row.isDraft) return `${row.name}: ${range}`
	if (row.isLinked) return `${row.name}: ${range} (linked — remove via chip below)`
	return `${row.name}: ${range} — click to depend on`
}

function onBarClick(row) {
	if (!row || row.isDraft || row.isLinked) return
	emit("select-task", {
		name: row.id,
		subject: row.name,
		exp_start_date: row.start,
		exp_end_date: row.end,
	})
}

function barStyle(row) {
	const days = timeline.value.days
	if (!days.length) return { display: "none" }

	let from = days.findIndex((d) => d.iso >= row.start)
	if (from < 0) {
		// Draft/task starts after the visible window
		return { display: "none" }
	}
	if (days[from].iso > row.end) {
		// Entirely before first day somehow
		return { display: "none" }
	}

	let to = from
	for (let i = days.length - 1; i >= from; i--) {
		if (days[i].iso <= row.end) {
			to = i
			break
		}
	}

	const left = from * COLUMN_WIDTH + 2
	const width = Math.max(COLUMN_WIDTH - 4, (to - from + 1) * COLUMN_WIDTH - 4)
	return { left: `${left}px`, width: `${width}px` }
}

async function loadContextTasks() {
	if (!props.startDate) {
		contextTasks.value = []
		return
	}
	loading.value = true
	loadError.value = ""
	try {
		contextTasks.value = await call(`${API.value}.get_tasks`, { include_completed: 0 })
	} catch (e) {
		loadError.value = e?.messages?.[0] || e?.message || "Could not load tasks"
		contextTasks.value = []
	} finally {
		loading.value = false
		await nextTick()
		scrollToDraft()
	}
}

const scheduleLoadContextTasks = debounce(() => {
	loadContextTasks()
}, 200)

function scrollToDraft() {
	const el = scrollEl.value
	const start = parseDate(props.startDate)
	if (!el || !start || !timeline.value.days.length) return
	el.scrollLeft = scrollLeftForDate(timeline.value, start, el.clientWidth - LABEL_WIDTH)
}

watch(
	() => [props.startDate, props.apiPrefix],
	([start]) => {
		if (start) scheduleLoadContextTasks()
		else {
			contextTasks.value = []
			loadError.value = ""
		}
	}
)

watch(
	() => [props.startDate, props.endDate, draftEnd.value, timeline.value.totalWidth],
	async () => {
		await nextTick()
		scrollToDraft()
	}
)

onMounted(() => {
	if (props.startDate) loadContextTasks()
})
</script>
