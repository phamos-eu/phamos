<template>
	<section v-if="visible" class="space-y-2">
		<div class="flex items-center justify-between gap-2">
			<label class="block text-xs text-ink-gray-5">
				{{ isNavigateMode ? "Task schedule" : "Schedule preview" }}
			</label>
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
			class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-4 text-xs text-ink-red-4"
		>
			{{ loadError }}
		</div>
		<div
			v-else
			ref="scrollEl"
			class="overflow-x-auto rounded-lg border border-outline-gray-2 bg-surface-white"
			:class="isNavigateMode ? 'cursor-pointer hover:border-outline-gray-3' : ''"
			:title="isNavigateMode ? `Open ${highlightTaskId}` : undefined"
			@click="onPreviewSurfaceClick"
		>
			<div class="relative" :style="{ width: `${timeline.totalWidth + LABEL_WIDTH}px`, minWidth: '100%' }">
				<!-- Header -->
				<div class="sticky top-0 z-[2] flex border-b border-outline-gray-2 bg-surface-gray-1">
					<div
						class="sticky left-0 z-[4] flex-shrink-0 border-r border-outline-gray-2 bg-surface-gray-1 px-2 py-1 text-[10px] font-medium uppercase tracking-wide text-ink-gray-5"
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
								:class="{ 'bg-surface-blue-1 font-semibold text-ink-blue-3': day.iso === todayIso }"
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
					:class="row.isFocus ? 'bg-surface-blue-1' : 'bg-surface-white'"
					:style="{ height: `${ROW_HEIGHT}px` }"
				>
					<div
						class="sticky left-0 z-[3] flex flex-shrink-0 items-center border-r border-outline-gray-2 px-2 text-xs"
						:class="row.isFocus ? 'bg-surface-blue-1' : 'bg-surface-white'"
						:style="{ width: `${LABEL_WIDTH}px` }"
						:title="row.name"
					>
						<span
							class="truncate"
							:class="labelClass(row)"
						>
							{{ row.name }}
						</span>
					</div>
					<div class="relative flex-1" :style="{ width: `${timeline.totalWidth}px` }">
						<div
							v-if="todayStrip"
							class="pointer-events-none absolute inset-y-0 z-0 bg-surface-blue-2/10"
							:style="{ left: `${todayStrip.left}px`, width: `${todayStrip.width}px` }"
						/>
						<div
							v-if="todayStrip"
							class="pointer-events-none absolute inset-y-0 z-0 w-px bg-surface-blue-2"
							:style="{ left: `${todayStrip.edgeLeft}px` }"
						/>
						<div
							class="absolute top-1.5 flex h-5 items-center overflow-hidden rounded px-1.5 text-[10px] font-medium"
							:class="barClass(row)"
							:style="barStyle(row)"
							:title="barTitle(row)"
							:role="barRole(row)"
							:tabindex="barRole(row) === 'button' ? 0 : undefined"
							@click.stop="onBarClick(row)"
							@keydown.enter.prevent="onBarClick(row)"
							@keydown.space.prevent="onBarClick(row)"
						>
							<span class="truncate">{{ row.name }}</span>
						</div>
					</div>
				</div>

				<svg
					v-if="dependencyArrows.length"
					class="pointer-events-none absolute left-0 top-0 z-[1] text-ink-green-2"
					:width="timeline.totalWidth + LABEL_WIDTH"
					:height="HEADER_HEIGHT + rows.length * ROW_HEIGHT"
					aria-hidden="true"
				>
					<path
						v-for="arrow in dependencyArrows"
						:key="arrow.fromId"
						:d="arrow.path"
						fill="none"
						stroke="currentColor"
						stroke-width="1.5"
						stroke-linecap="round"
						stroke-linejoin="round"
					/>
				</svg>

				<div
					v-if="!rows.length"
					class="flex h-16 items-center justify-center text-xs text-ink-gray-5"
				>
					No overlapping tasks in this window
				</div>
			</div>
		</div>
		<p class="text-[11px] text-ink-gray-5">
			<span class="inline-block h-2 w-2 rounded-sm bg-surface-blue-1 ring-1 ring-outline-blue-2 align-middle" />
			{{ isNavigateMode ? "Converted task" : "New task" }}
			<span class="mx-1.5 text-ink-gray-4">·</span>
			{{
				isNavigateMode
					? "Click the preview to open it on the Gantt"
					: "Click a nearby task to toggle a finish → start dependency"
			}}
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
import { orthogonalDependencyPath } from "@spa/utils/ganttDependencyArrows.js"
import spaConfig from "@/config"

const LABEL_WIDTH = 140
const ROW_HEIGHT = 32
const HEADER_HEIGHT = 40
const BAR_TOP = 6
const BAR_HEIGHT = 20
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
	/** When set, centers on this existing Task and clicking opens it. */
	highlightTaskId: { type: String, default: "" },
})

const emit = defineEmits(["select-task", "open"])

const API = computed(() => props.apiPrefix || spaConfig.api)
const isNavigateMode = computed(() => Boolean(String(props.highlightTaskId || "").trim()))
const scrollEl = ref(null)
const loading = ref(false)
const loadError = ref("")
const contextTasks = ref([])
const focusTask = ref(null)

const linkedSet = computed(() => new Set((props.linkedTaskIds || []).map(String)))

const todayIso = computed(() => todayIsoInUserTz())

const effectiveStartDate = computed(() => {
	if (isNavigateMode.value) {
		return String(focusTask.value?.exp_start_date || "").slice(0, 10)
	}
	return String(props.startDate || "").trim()
})

const effectiveEndDate = computed(() => {
	if (isNavigateMode.value) {
		const start = String(focusTask.value?.exp_start_date || "").slice(0, 10)
		const end = String(focusTask.value?.exp_end_date || start).slice(0, 10)
		return end && end >= start ? end : start
	}
	return String(props.endDate || "").trim()
})

const effectiveSubject = computed(() => {
	if (isNavigateMode.value) {
		return focusTask.value?.subject || focusTask.value?.name || props.highlightTaskId
	}
	return props.subject
})

const visible = computed(() => Boolean(effectiveStartDate.value || isNavigateMode.value))

const draftEnd = computed(() => {
	const start = effectiveStartDate.value
	const end = effectiveEndDate.value
	if (!start) return ""
	if (end && end >= start) return end
	return start
})

const rangeLabel = computed(() => {
	if (!effectiveStartDate.value) return ""
	const end = draftEnd.value
	if (!end || end === effectiveStartDate.value) return formatDate(effectiveStartDate.value)
	return `${formatDate(effectiveStartDate.value)} – ${formatDate(end)}`
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
	const start = parseDate(effectiveStartDate.value)
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
	const start = parseDate(effectiveStartDate.value)
	const end = parseDate(draftEnd.value)
	if (!start || !end || !frame.value) return []

	const focusId = isNavigateMode.value ? String(props.highlightTaskId) : "__draft__"
	const focus = {
		id: focusId,
		name: (effectiveSubject.value || "").trim() || (isNavigateMode.value ? focusId : "New task"),
		start: formatDateIso(start),
		end: formatDateIso(end),
		isFocus: true,
		isLinked: false,
	}

	// Pick nearby tasks by schedule proximity, then place all rows
	// chronologically (same idea as the real Gantt) so the focus task
	// sits in its natural date order instead of always on top.
	const nearby = contextTasks.value
		.filter((t) => String(t.name) !== focusId)
		.filter((t) => overlapsWindow(t, frame.value.start, frame.value.end))
		.map((t) => ({
			task: t,
			distance: distanceToDraft(t, start, end),
		}))
		.sort(
			(a, b) =>
				a.distance - b.distance ||
				String(a.task.exp_start_date).localeCompare(String(b.task.exp_start_date))
		)
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
				isFocus: false,
				isLinked: !isNavigateMode.value && linkedSet.value.has(String(task.name)),
			}
		})

	return [focus, ...nearby].sort(
		(a, b) => a.start.localeCompare(b.start) || a.end.localeCompare(b.end) || a.name.localeCompare(b.name)
	)
})

function labelClass(row) {
	if (row.isFocus) return "font-semibold text-ink-gray-9"
	if (row.isLinked) return "font-medium text-ink-green-3"
	return "text-ink-gray-7"
}

function barClass(row) {
	if (row.isFocus) {
		// Light blue surface + dark blue ink stays readable in light mode
		// (avoid text-white on pale blue).
		return "bg-surface-blue-1 text-ink-blue-3 shadow-sm ring-2 ring-outline-blue-2"
	}
	if (row.isLinked) {
		// Light green surface + dark green ink stays readable in light mode
		// (avoid text-white, which washes out if the bar sits on gray).
		return "cursor-pointer bg-surface-green-2 text-ink-green-3 ring-2 ring-outline-green-2"
	}
	if (isNavigateMode.value) {
		return "bg-surface-gray-3 text-ink-gray-8"
	}
	return "cursor-pointer bg-surface-gray-3 text-ink-gray-8 hover:bg-surface-gray-4"
}

function barTitle(row) {
	const range = `${formatDate(row.start)} – ${formatDate(row.end)}`
	if (isNavigateMode.value) {
		if (row.isFocus) return `${row.name}: ${range} — click to open`
		return `${row.name}: ${range}`
	}
	if (row.isFocus) return `${row.name}: ${range}`
	if (row.isLinked) return `${row.name}: ${range} — click to remove dependency`
	return `${row.name}: ${range} — click to depend on`
}

function barRole(row) {
	if (isNavigateMode.value) return row.isFocus ? "button" : undefined
	if (row.isFocus) return undefined
	return "button"
}

function onPreviewSurfaceClick() {
	if (!isNavigateMode.value) return
	emit("open", { name: props.highlightTaskId })
}

function onBarClick(row) {
	if (!row) return
	if (isNavigateMode.value) {
		emit("open", { name: props.highlightTaskId })
		return
	}
	if (row.isFocus) return
	emit("select-task", {
		name: row.id,
		subject: row.name,
		exp_start_date: row.start,
		exp_end_date: row.end,
	})
}

function barMetrics(row) {
	const days = timeline.value.days
	if (!days.length) return null

	let from = days.findIndex((d) => d.iso >= row.start)
	if (from < 0) return null
	if (days[from].iso > row.end) return null

	let to = from
	for (let i = days.length - 1; i >= from; i--) {
		if (days[i].iso <= row.end) {
			to = i
			break
		}
	}

	const left = from * COLUMN_WIDTH + 2
	const width = Math.max(COLUMN_WIDTH - 4, (to - from + 1) * COLUMN_WIDTH - 4)
	return { left, width }
}

function barStyle(row) {
	const metrics = barMetrics(row)
	if (!metrics) return { display: "none" }
	return { left: `${metrics.left}px`, width: `${metrics.width}px` }
}

function barMidY(rowIndex) {
	return HEADER_HEIGHT + rowIndex * ROW_HEIGHT + BAR_TOP + BAR_HEIGHT / 2
}

const dependencyArrows = computed(() => {
	if (isNavigateMode.value) return []
	const list = rows.value
	if (!list.length || !linkedSet.value.size) return []

	const focusIndex = list.findIndex((r) => r.isFocus)
	if (focusIndex < 0) return []
	const focusMetrics = barMetrics(list[focusIndex])
	if (!focusMetrics) return []

	const endX = LABEL_WIDTH + focusMetrics.left
	const endY = barMidY(focusIndex)
	const arrows = []
	let lane = 0

	list.forEach((row, idx) => {
		if (!row.isLinked) return
		const metrics = barMetrics(row)
		if (!metrics) return
		const startX = LABEL_WIDTH + metrics.left + metrics.width
		const startY = barMidY(idx)
		arrows.push({
			fromId: row.id,
			path: orthogonalDependencyPath(startX, startY, endX, endY, lane),
		})
		lane += 1
	})

	return arrows
})

async function resolveFocusTask(tasks) {
	const name = String(props.highlightTaskId || "").trim()
	if (!name) {
		focusTask.value = null
		return
	}
	let found = (tasks || []).find((t) => String(t.name) === name)
	if (!found) {
		try {
			found = await call(`${API.value}.get_task`, { name })
		} catch (e) {
			found = null
			throw e
		}
	}
	focusTask.value = found
}

async function loadContextTasks() {
	if (!props.startDate && !isNavigateMode.value) {
		contextTasks.value = []
		focusTask.value = null
		return
	}
	loading.value = true
	loadError.value = ""
	try {
		const includeCompleted = isNavigateMode.value ? 1 : 0
		contextTasks.value = await call(`${API.value}.get_tasks`, {
			include_completed: includeCompleted,
		})
		if (isNavigateMode.value) {
			await resolveFocusTask(contextTasks.value)
			if (!focusTask.value?.exp_start_date) {
				loadError.value = "Converted task has no schedule dates"
			}
		} else {
			focusTask.value = null
		}
	} catch (e) {
		loadError.value = e?.messages?.[0] || e?.message || "Could not load tasks"
		contextTasks.value = []
		focusTask.value = null
	} finally {
		loading.value = false
		await nextTick()
		scrollToFocus()
	}
}

const scheduleLoadContextTasks = debounce(() => {
	loadContextTasks()
}, 200)

function scrollToFocus() {
	const el = scrollEl.value
	const start = parseDate(effectiveStartDate.value)
	if (!el || !start || !timeline.value.days.length) return
	el.scrollLeft = scrollLeftForDate(timeline.value, start, el.clientWidth - LABEL_WIDTH)
}

watch(
	() => [props.startDate, props.highlightTaskId, props.apiPrefix],
	([start, highlight]) => {
		if (start || highlight) scheduleLoadContextTasks()
		else {
			contextTasks.value = []
			focusTask.value = null
			loadError.value = ""
		}
	}
)

watch(
	() => [
		effectiveStartDate.value,
		effectiveEndDate.value,
		draftEnd.value,
		timeline.value.totalWidth,
	],
	async () => {
		await nextTick()
		scrollToFocus()
	}
)

onMounted(() => {
	if (props.startDate || isNavigateMode.value) loadContextTasks()
})
</script>
