<template>
	<div class="hr-gantt flex min-h-0 flex-1 flex-col">
		<div class="hr-gantt-main flex min-h-0 flex-1">
			<div
				class="hr-gantt-left flex flex-shrink-0 flex-col border-r border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900"
				:style="{ width: `${LIST_WIDTH}px` }"
			>
				<div
					class="hr-gantt-corner flex flex-shrink-0 items-center gap-1.5 border-b border-gray-200 bg-gray-50 px-2 dark:border-gray-700 dark:bg-gray-800"
					:style="{ height: `${TIMELINE_CONTROLS_HEIGHT}px` }"
				>
					<input
						:value="search"
						type="search"
						class="min-w-0 flex-1 rounded border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
						placeholder="Search…"
						@input="emit('update:search', $event.target.value)"
					/>
					<div class="hr-gantt-filter relative flex-shrink-0">
						<button
							type="button"
							class="flex h-7 w-7 items-center justify-center rounded border border-gray-300 bg-white text-gray-600 hover:bg-gray-100 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
							:class="{ 'border-gray-900 text-gray-900 dark:border-gray-300 dark:text-gray-100': includeCompleted }"
							aria-label="Filter tasks"
							@click.stop="toggleFilterMenu"
						>
							<FeatherIcon name="filter" class="h-3.5 w-3.5" />
						</button>
						<div
							v-if="filterMenuOpen"
							class="hr-gantt-filter-menu absolute right-0 top-full z-20 mt-1 w-44 rounded-md border border-gray-200 bg-white py-1 shadow-lg dark:border-gray-700 dark:bg-gray-800"
						>
							<button
								type="button"
								class="block w-full px-3 py-1.5 text-left text-xs hover:bg-gray-50 dark:hover:bg-gray-700"
								:class="!includeCompleted ? 'font-medium text-gray-900 dark:text-gray-100' : 'text-gray-600 dark:text-gray-400'"
								@click="setIncludeCompleted(false)"
							>
								Active tasks
							</button>
							<button
								type="button"
								class="block w-full px-3 py-1.5 text-left text-xs hover:bg-gray-50 dark:hover:bg-gray-700"
								:class="includeCompleted ? 'font-medium text-gray-900 dark:text-gray-100' : 'text-gray-600 dark:text-gray-400'"
								@click="setIncludeCompleted(true)"
							>
								Include completed
							</button>
						</div>
					</div>
				</div>
				<div
					class="hr-gantt-header-spacer flex-shrink-0 border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800"
					:style="{ height: `${HEADER_TOTAL}px` }"
				/>
				<div
					ref="listScroll"
					class="hr-gantt-list min-h-0 flex-1 overflow-hidden"
					@scroll="onListScroll"
				>
					<div :style="{ paddingTop: `${LIST_TOP_OFFSET}px` }">
						<button
							v-for="task in ganttTasks"
							:key="task.id"
							type="button"
							class="hr-gantt-list-row flex w-full items-center gap-2 border-b border-gray-100 px-3 text-left text-xs text-gray-800 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-200 dark:hover:bg-gray-800"
							:class="{ 'hr-gantt-list-row--selected': task.id === selectedName }"
							:style="{ height: `${ROW_HEIGHT}px` }"
							@click="emit('select', task.id)"
						>
							<span class="min-w-0 flex-1 truncate font-medium">{{ task.name }}</span>
							<span
								v-if="taskStatus(task.id)"
								class="flex-shrink-0 rounded px-1.5 py-0.5 text-[10px] text-gray-500 dark:text-gray-400"
							>
								{{ taskStatus(task.id) }}
							</span>
						</button>
					</div>
					<div v-if="undatedTasks.length" class="border-t border-gray-200 dark:border-gray-700">
						<p class="px-3 py-1.5 text-[10px] font-medium uppercase tracking-wide text-gray-400">
							No dates
						</p>
						<button
							v-for="task in undatedTasks"
							:key="task.name"
							type="button"
							class="hr-gantt-list-row flex w-full items-center gap-2 border-b border-gray-100 px-3 text-left text-xs text-gray-600 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-400 dark:hover:bg-gray-800"
							:class="{ 'hr-gantt-list-row--selected': task.name === selectedName }"
							:style="{ height: `${ROW_HEIGHT}px` }"
							@click="emit('select', task.name)"
						>
							<span class="min-w-0 flex-1 truncate">{{ task.subject || task.name }}</span>
						</button>
					</div>
				</div>
				<div class="hr-gantt-list-footer flex-shrink-0 border-t border-gray-200 bg-gray-50 p-2 dark:border-gray-700 dark:bg-gray-800">
					<form class="flex gap-1.5" @submit.prevent="submitNewTask">
						<input
							ref="newTaskInput"
							v-model="newTaskSubject"
							type="text"
							class="min-w-0 flex-1 rounded border border-gray-300 bg-white px-2 py-1.5 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
							placeholder="New task…"
							:disabled="creatingTask"
						/>
						<button
							type="submit"
							class="flex-shrink-0 rounded bg-gray-900 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-gray-800 disabled:opacity-50 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-gray-200"
							:disabled="creatingTask || !newTaskSubject.trim()"
						>
							{{ creatingTask ? "…" : "Add" }}
						</button>
					</form>
					<p v-if="createError" class="mt-1 text-[11px] text-red-600 dark:text-red-400">{{ createError }}</p>
				</div>
			</div>

			<div
				class="hr-gantt-right flex min-w-0 flex-1 flex-col"
				:class="{ 'hr-gantt--link-mode': linkMode }"
			>
				<div
					class="hr-gantt-timeline-controls flex flex-shrink-0 items-center gap-3 border-b border-gray-200 bg-gray-50 px-3 dark:border-gray-700 dark:bg-gray-800"
					:style="{ height: `${TIMELINE_CONTROLS_HEIGHT}px` }"
				>
					<label class="flex items-center gap-1.5 text-[11px] text-gray-600 dark:text-gray-400">
						<span>Start</span>
						<input
							v-model="frameStart"
							type="date"
							class="rounded border border-gray-300 bg-white px-1.5 py-0.5 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
							@change="onFrameChange"
						/>
					</label>
					<label class="flex items-center gap-1.5 text-[11px] text-gray-600 dark:text-gray-400">
						<span>End</span>
						<input
							v-model="frameEnd"
							type="date"
							class="rounded border border-gray-300 bg-white px-1.5 py-0.5 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
							@change="onFrameChange"
						/>
					</label>
					<span
						v-if="selectionRangeLabel"
						class="text-[11px] font-medium text-blue-600 dark:text-blue-400"
					>
						{{ selectionRangeLabel }}
					</span>
					<button
						type="button"
						class="rounded border px-2 py-0.5 text-[11px] font-medium transition"
						:class="
							linkMode
								? 'border-blue-600 bg-blue-50 text-blue-700 dark:border-blue-400 dark:bg-blue-950 dark:text-blue-300'
								: 'border-gray-300 bg-white text-gray-600 hover:bg-gray-100 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'
						"
						:title="linkMode ? 'Click predecessor, then successor (Esc to cancel)' : 'Link tasks'"
						@click="toggleLinkMode"
					>
						Link
					</button>
					<label class="ml-auto flex items-center gap-2 text-[11px] text-gray-600 dark:text-gray-400">
						Zoom
						<input
							v-model.number="zoom"
							type="range"
							min="18"
							max="48"
							step="2"
							class="w-24"
						/>
					</label>
				</div>
				<div
					ref="headerScroll"
					class="hr-gantt-header-scroll flex-shrink-0 overflow-x-auto border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800"
					@scroll="onHeaderScroll"
					@wheel="onHeaderWheel"
				>
					<div class="relative" :style="{ width: `${timeline.totalWidth}px` }">
						<div
							v-if="todayStrip"
							class="hr-gantt-today-strip"
							:style="{ left: `${todayStrip.left}px`, width: `${todayStrip.width}px` }"
						/>
						<div
							v-if="todayStrip"
							class="hr-gantt-today-strip-edge"
							:style="{ left: `${todayStrip.edgeLeft}px` }"
						/>
						<div
							v-if="selectionBandStyle"
							class="hr-gantt-selection"
							:style="selectionBandStyle"
						/>
						<div
							class="hr-gantt-header-hit"
							@pointerdown="onHeaderPointerDown"
							@pointermove="onHeaderPointerMove"
							@pointerup="onHeaderPointerUp"
							@pointercancel="onHeaderPointerUp"
						>
							<div class="hr-gantt-header-row hr-gantt-header-row--month">
								<button
									v-for="(month, idx) in timeline.months"
									:key="`m-${idx}`"
									type="button"
									class="hr-gantt-header-cell hr-gantt-header-cell--clickable"
									:style="{ width: `${month.width}px` }"
									@click.stop="setFrameFromSegment(month.startIso, month.endIso)"
								>
									{{ month.label }}
								</button>
							</div>
							<div class="hr-gantt-header-row hr-gantt-header-row--week">
								<button
									v-for="(week, idx) in timeline.weeks"
									:key="`w-${idx}`"
									type="button"
									class="hr-gantt-header-cell hr-gantt-header-cell--clickable"
									:style="{ width: `${week.width}px` }"
									@click.stop="setFrameFromSegment(week.startIso, week.endIso)"
								>
									W{{ week.number }}
								</button>
							</div>
							<div class="hr-gantt-header-row hr-gantt-header-row--day">
								<button
									v-for="day in timeline.days"
									:key="day.iso"
									type="button"
									class="hr-gantt-header-cell hr-gantt-header-cell--day hr-gantt-header-cell--clickable"
									:style="{ width: `${day.width}px` }"
									@click.stop="setFrameFromSegment(day.iso, day.iso)"
								>
									{{ day.label }}
								</button>
							</div>
						</div>
					</div>
				</div>

				<div
					ref="bodyScroll"
					class="hr-gantt-body min-h-0 flex-1 overflow-auto"
					@scroll="onBodyScroll"
				>
					<div
						class="hr-gantt-body-inner relative"
						:style="bodyInnerStyle"
					>
						<div
							v-if="!ganttTasks.length"
							class="absolute inset-0 flex items-center justify-center text-xs text-gray-400 dark:text-gray-500 z-[3]"
						>
							Set expected dates to show tasks on the timeline
						</div>
						<div ref="ganttHost" class="hr-gantt-wrap" />
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue"
import Gantt from "frappe-gantt"
import { call } from "frappe-ui"
import { formatDate, todayIsoInUserTz } from "@iown/utils/datetime"
import {
	buildTimeline,
	defaultFrameRange,
	expandFrameToTasks,
	normalizeFrameRange,
	scrollLeftForDate,
	todayStripRect,
} from "../utils/ganttTimeline"
import { formatDateIso } from "../utils/ganttTimelineFormat"
import { buildBarColorCss, parseDependsOn, taskColorClass } from "../utils/ganttColors"
import { restyleDependencyArrows } from "../utils/ganttDependencyArrows"
import { updateGanttTodayStrip } from "../utils/ganttTodayStrip"
import spaConfig from "@/config"

const API = spaConfig.api
const BAR_COLOR_STYLE_ID = spaConfig.barColorStyleId || `${spaConfig.slug}-gantt-bar-colors`

const props = defineProps({
	tasks: { type: Array, default: () => [] },
	selectedName: { type: String, default: null },
	search: { type: String, default: "" },
	includeCompleted: { type: Boolean, default: false },
})

const emit = defineEmits([
	"select",
	"date-change",
	"dependency-change",
	"created",
	"update:search",
	"update:includeCompleted",
])

const BAR_HEIGHT = 24
const ROW_PADDING = 18
const ROW_HEIGHT = BAR_HEIGHT + ROW_PADDING
const LIST_TOP_OFFSET = ROW_PADDING / 2
const HEADER_TOTAL = 26 + 22 + 26
const TIMELINE_CONTROLS_HEIGHT = 36
const LIST_WIDTH = 240
const DRAG_THRESHOLD_PX = 4

const ganttHost = ref(null)
const headerScroll = ref(null)
const bodyScroll = ref(null)
const listScroll = ref(null)
const newTaskInput = ref(null)
const bodyViewportHeight = ref(0)
/** Bumps periodically so the now-line tracks the clock. */
const nowTick = ref(Date.now())

let bodyResizeObserver = null
let nowTickTimer = null

const zoom = ref(38)
const frameStart = ref("")
const frameEnd = ref("")
const newTaskSubject = ref("")
const creatingTask = ref(false)
const createError = ref("")
const filterMenuOpen = ref(false)
const linkMode = ref(false)
const linkFrom = ref(null)

const selecting = ref(false)
const selectionStartCol = ref(null)
const selectionEndCol = ref(null)
const selectionDragActive = ref(false)
const pointerStartX = ref(0)

let gantt = null
let syncingScroll = false
let lastTimelineWidth = 0

const timeline = computed(() => {
	const start = parseDate(frameStart.value)
	const end = parseDate(frameEnd.value)
	if (!start || !end) {
		return {
			days: [],
			weeks: [],
			months: [],
			totalWidth: 0,
			rangeStart: null,
			rangeEnd: null,
		}
	}
	return buildTimeline(start, end, zoom.value, zoom.value)
})

const ganttTasks = computed(() =>
	props.tasks
		.filter((t) => t.exp_start_date)
		.map((t) => {
			const start = t.exp_start_date
			let end = t.exp_end_date || t.exp_start_date
			if (end < start) end = start
			const classes = []
			const colorCls = taskColorClass(t.color)
			if (colorCls) classes.push(colorCls)
			if (t.name === props.selectedName) classes.push("bar-selected")
			return {
				id: t.name,
				name: t.subject || t.name,
				start,
				end,
				progress: Math.min(100, Math.max(0, Number(t.progress) || 0)),
				dependencies: parseDependsOn(t.depends_on_tasks),
				custom_class: classes.join(" "),
			}
		})
)

const undatedTasks = computed(() => props.tasks.filter((t) => !t.exp_start_date))

const todayStrip = computed(() => {
	void nowTick.value
	return todayStripRect(timeline.value)
})

const bodyInnerMinHeightPx = computed(() =>
	Math.max(ganttTasks.value.length ? 0 : 120, bodyViewportHeight.value)
)

const bodyInnerStyle = computed(() => {
	const minH = bodyInnerMinHeightPx.value
	return {
		width: `${timeline.value.totalWidth}px`,
		minHeight: minH > 0 ? `${minH}px` : undefined,
	}
})

const selectionBandStyle = computed(() => {
	if (selectionStartCol.value === null || selectionEndCol.value === null) return null
	const minCol = Math.min(selectionStartCol.value, selectionEndCol.value)
	const maxCol = Math.max(selectionStartCol.value, selectionEndCol.value)
	return {
		left: `${minCol * zoom.value}px`,
		width: `${(maxCol - minCol + 1) * zoom.value}px`,
	}
})

const selectionRangeLabel = computed(() => {
	if (!selectionDragActive.value || selectionStartCol.value === null || selectionEndCol.value === null) {
		return ""
	}
	const days = timeline.value.days
	if (!days.length) return ""
	const minCol = Math.min(selectionStartCol.value, selectionEndCol.value)
	const maxCol = Math.max(selectionStartCol.value, selectionEndCol.value)
	const startDay = days[minCol]
	const endDay = days[maxCol]
	if (!startDay || !endDay) return ""
	return `${formatDate(startDay.iso)} – ${formatDate(endDay.iso)}`
})

const taskStatusMap = computed(() => {
	const map = {}
	for (const t of props.tasks) {
		if (t.name) map[t.name] = t.status || ""
	}
	return map
})

function taskStatus(id) {
	return taskStatusMap.value[id] || ""
}

function toggleFilterMenu() {
	filterMenuOpen.value = !filterMenuOpen.value
}

function setIncludeCompleted(value) {
	filterMenuOpen.value = false
	if (props.includeCompleted !== value) {
		emit("update:includeCompleted", value)
	}
}

function toggleLinkMode() {
	linkMode.value = !linkMode.value
	if (!linkMode.value) {
		linkFrom.value = null
		updateBarStateClasses()
	}
}

function onDocumentClick(e) {
	if (!filterMenuOpen.value) return
	const el = e.target
	if (el instanceof Element && el.closest(".hr-gantt-filter")) return
	filterMenuOpen.value = false
}

function onKeyDown(e) {
	if (e.key === "Escape" && linkMode.value) {
		linkMode.value = false
		linkFrom.value = null
		updateBarStateClasses()
	}
}

function collectTaskDates() {
	return props.tasks
		.filter((t) => t.exp_start_date)
		.flatMap((t) => {
			const start = parseDate(t.exp_start_date)
			const end = parseDate(t.exp_end_date || t.exp_start_date)
			return [start, end].filter(Boolean)
		})
}

function initFrame() {
	const def = defaultFrameRange()
	const taskDates = collectTaskDates()
	const { start, end } = expandFrameToTasks(taskDates, def.start, def.end)
	frameStart.value = formatDateIso(start)
	frameEnd.value = formatDateIso(end)
}

function normalizeFrameInputs() {
	const start = parseDate(frameStart.value)
	const end = parseDate(frameEnd.value)
	if (!start || !end) return
	const normalized = normalizeFrameRange(start, end)
	frameStart.value = formatDateIso(normalized.start)
	frameEnd.value = formatDateIso(normalized.end)
}

function getFrameDates() {
	const start = parseDate(frameStart.value)
	const endInclusive = parseDate(frameEnd.value)
	if (!start || !endInclusive) return null
	const normalized = normalizeFrameRange(start, endInclusive)
	const frameStartDate = normalized.start
	const frameEndExclusive = new Date(normalized.end)
	frameEndExclusive.setDate(frameEndExclusive.getDate() + 1)
	frameEndExclusive.setHours(0, 0, 0, 0)
	return { frameStartDate, frameEndExclusive }
}

function setFrameFromSegment(startIso, endIso) {
	if (!startIso || !endIso || selecting.value) return
	clearSelectionBand()
	frameStart.value = startIso
	frameEnd.value = endIso
	onFrameChange()
}

function clearSelectionBand() {
	selectionStartCol.value = null
	selectionEndCol.value = null
	selectionDragActive.value = false
}

function colFromClientX(clientX) {
	const el = headerScroll.value
	if (!el || !timeline.value.days.length) return 0
	const rect = el.getBoundingClientRect()
	const x = clientX - rect.left + el.scrollLeft
	const col = Math.floor(x / zoom.value)
	return Math.max(0, Math.min(col, timeline.value.days.length - 1))
}

function onHeaderPointerDown(e) {
	if (linkMode.value || e.button !== 0) return
	selecting.value = true
	selectionDragActive.value = false
	pointerStartX.value = e.clientX
	const col = colFromClientX(e.clientX)
	selectionStartCol.value = col
	selectionEndCol.value = col
	e.currentTarget?.setPointerCapture?.(e.pointerId)
}

function onHeaderPointerMove(e) {
	if (!selecting.value || selectionStartCol.value === null) return
	if (Math.abs(e.clientX - pointerStartX.value) >= DRAG_THRESHOLD_PX) {
		selectionDragActive.value = true
	}
	selectionEndCol.value = colFromClientX(e.clientX)
}

function onHeaderPointerUp() {
	if (!selecting.value) return
	selecting.value = false

	if (selectionDragActive.value && selectionStartCol.value !== null && selectionEndCol.value !== null) {
		const days = timeline.value.days
		const minCol = Math.min(selectionStartCol.value, selectionEndCol.value)
		const maxCol = Math.max(selectionStartCol.value, selectionEndCol.value)
		const startDay = days[minCol]
		const endDay = days[maxCol]
		if (startDay && endDay) {
			frameStart.value = startDay.iso
			frameEnd.value = endDay.iso
			onFrameChange()
		}
	} else {
		clearSelectionBand()
	}
}

function todayIso() {
	return todayIsoInUserTz()
}

function todayDate() {
	const iso = todayIsoInUserTz()
	const [y, mo, dd] = iso.split("-").map(Number)
	return new Date(y, mo - 1, dd, 0, 0, 0, 0)
}

async function submitNewTask() {
	const subject = newTaskSubject.value.trim()
	if (!subject || creatingTask.value) return

	creatingTask.value = true
	createError.value = ""
	try {
		const task = await call(`${API}.create_task`, {
			subject,
			exp_start_date: todayIso(),
		})
		newTaskSubject.value = ""
		emit("created", task.name)
	} catch (e) {
		createError.value = e?.messages?.[0] || e?.message || "Could not create task"
	} finally {
		creatingTask.value = false
		nextTick(() => newTaskInput.value?.focus())
	}
}

function parseDate(value) {
	if (!value) return null
	const d = new Date(value)
	return Number.isNaN(d.getTime()) ? null : d
}

function destroyGantt() {
	if (ganttHost.value) ganttHost.value.innerHTML = ""
	gantt = null
}

function fixSvgWidth() {
	if (!gantt || !timeline.value.totalWidth) return
	const svg = ganttHost.value?.querySelector("svg.gantt")
	if (svg) svg.setAttribute("width", String(timeline.value.totalWidth))
}

function injectBarColors() {
	let el = document.getElementById(BAR_COLOR_STYLE_ID)
	if (!el) {
		el = document.createElement("style")
		el.id = BAR_COLOR_STYLE_ID
		document.head.appendChild(el)
	}
	el.textContent = buildBarColorCss(ganttTasks.value)
}

function updateTodayStripOverlay() {
	if (!gantt) return
	updateGanttTodayStrip(gantt, todayStrip.value, bodyInnerMinHeightPx.value)
}

function applyGanttFrame() {
	if (!gantt) return
	const frame = getFrameDates()
	if (!frame) return

	gantt.gantt_start = frame.frameStartDate
	gantt.gantt_end = frame.frameEndExclusive
	gantt.setup_date_values()
	gantt.options.column_width = zoom.value
	gantt.render()
	fixSvgWidth()
	updateBarStateClasses()
	restyleDependencyArrows(gantt)
	updateTodayStripOverlay()
}

function handleLinkClick(taskId) {
	if (!linkFrom.value) {
		linkFrom.value = taskId
		updateBarStateClasses()
		return
	}
	if (linkFrom.value === taskId) {
		linkFrom.value = null
		updateBarStateClasses()
		return
	}
	emit("dependency-change", { name: taskId, depends_on: linkFrom.value })
	linkMode.value = false
	linkFrom.value = null
	updateBarStateClasses()
}

function buildGantt() {
	destroyGantt()
	if (!ganttHost.value) return

	injectBarColors()
	const tasksForGantt = ganttTasks.value

	gantt = new Gantt(ganttHost.value, tasksForGantt, {
		view_mode: "Day",
		column_width: zoom.value,
		bar_height: BAR_HEIGHT,
		padding: ROW_PADDING,
		header_height: 0,
		date_format: "YYYY-MM-DD",
		language: "en",
		on_click: (task) => {
			if (linkMode.value) {
				handleLinkClick(task.id)
				return
			}
			emit("select", task.id)
		},
		on_date_change: (task, start, end) => {
			emit("date-change", {
				name: task.id,
				exp_start_date: formatDateIso(start),
				exp_end_date: formatDateIso(end),
			})
		},
	})

	applyGanttFrame()

	nextTick(() => {
		lastTimelineWidth = timeline.value.totalWidth
		if (isTodayInFrame()) {
			scrollToToday(false)
		}
	})
}

function isTodayInFrame() {
	const frame = getFrameDates()
	if (!frame) return false
	const today = todayDate()
	return today >= frame.frameStartDate && today < frame.frameEndExclusive
}

function applyZoom() {
	if (!gantt) return
	const body = bodyScroll.value
	const oldWidth = lastTimelineWidth || timeline.value.totalWidth
	const scrollRatio = body && oldWidth ? body.scrollLeft / oldWidth : 0

	applyGanttFrame()

	nextTick(() => {
		if (body) {
			body.scrollLeft = scrollRatio * timeline.value.totalWidth
			syncHeaderScroll()
		}
		lastTimelineWidth = timeline.value.totalWidth
	})
}

function updateBarStateClasses() {
	if (!gantt?.bars) return
	for (const bar of gantt.bars) {
		const selected = bar.task.id === props.selectedName
		const linkSource = bar.task.id === linkFrom.value
		bar.group.classList.toggle("bar-selected", selected)
		bar.group.classList.toggle("link-from", linkSource)
	}
}

function updateBodyViewportHeight() {
	if (bodyScroll.value) {
		bodyViewportHeight.value = bodyScroll.value.clientHeight
	}
	updateTodayStripOverlay()
}

function scrollToToday(smooth = false) {
	const body = bodyScroll.value
	if (!body || !timeline.value.days.length) return
	const left = scrollLeftForDate(timeline.value, todayDate(), body.clientWidth)
	body.scrollTo({ left, behavior: smooth ? "smooth" : "auto" })
	syncHeaderScroll()
}

function syncHeaderScroll() {
	if (!headerScroll.value || !bodyScroll.value) return
	headerScroll.value.scrollLeft = bodyScroll.value.scrollLeft
}

function onBodyScroll() {
	if (syncingScroll) return
	syncingScroll = true
	syncHeaderScroll()
	if (listScroll.value) {
		listScroll.value.scrollTop = bodyScroll.value.scrollTop
	}
	syncingScroll = false
}

function onHeaderScroll() {
	if (syncingScroll) return
	syncingScroll = true
	if (bodyScroll.value && headerScroll.value) {
		bodyScroll.value.scrollLeft = headerScroll.value.scrollLeft
	}
	syncingScroll = false
}

function onHeaderWheel(e) {
	const el = headerScroll.value
	if (!el) return
	const delta = e.shiftKey ? e.deltaY : e.deltaX || e.deltaY
	if (!delta) return
	e.preventDefault()
	el.scrollLeft += delta
}

function onFrameChange() {
	normalizeFrameInputs()
	clearSelectionBand()
	if (gantt) {
		applyGanttFrame()
		nextTick(() => {
			lastTimelineWidth = timeline.value.totalWidth
			if (isTodayInFrame()) scrollToToday(false)
		})
	} else {
		buildGantt()
	}
}

function onWheel(e) {
	if (!e.ctrlKey && !e.metaKey) return
	e.preventDefault()
	const delta = e.deltaY > 0 ? -2 : 2
	zoom.value = Math.min(48, Math.max(18, zoom.value + delta))
}

let ganttTasksSignature = ""

function tasksSignature(tasks) {
	return tasks
		.map(
			(t) =>
				`${t.id}:${t.start}:${t.end}:${t.progress}:${t.custom_class}:${(t.dependencies || []).join(",")}`
		)
		.join("|")
}

watch(
	() => tasksSignature(ganttTasks.value),
	(sig) => {
		if (sig === ganttTasksSignature) return
		ganttTasksSignature = sig
		buildGantt()
	}
)

watch(zoom, () => {
	if (!gantt) {
		buildGantt()
		return
	}
	applyZoom()
})

watch(
	() => props.selectedName,
	() => updateBarStateClasses()
)

watch(todayStrip, () => updateTodayStripOverlay())

watch(linkFrom, () => updateBarStateClasses())

onMounted(() => {
	initFrame()
	document.addEventListener("click", onDocumentClick)
	document.addEventListener("keydown", onKeyDown)
	ganttTasksSignature = tasksSignature(ganttTasks.value)
	buildGantt()
	bodyScroll.value?.addEventListener("wheel", onWheel, { passive: false })
	nowTickTimer = setInterval(() => {
		nowTick.value = Date.now()
	}, 60_000)
	nextTick(() => {
		updateBodyViewportHeight()
		if (bodyScroll.value) {
			bodyResizeObserver = new ResizeObserver(() => updateBodyViewportHeight())
			bodyResizeObserver.observe(bodyScroll.value)
		}
	})
})

onUnmounted(() => {
	if (nowTickTimer) {
		clearInterval(nowTickTimer)
		nowTickTimer = null
	}
	bodyResizeObserver?.disconnect()
	bodyResizeObserver = null
	document.removeEventListener("click", onDocumentClick)
	document.removeEventListener("keydown", onKeyDown)
	bodyScroll.value?.removeEventListener("wheel", onWheel)
	document.getElementById(BAR_COLOR_STYLE_ID)?.remove()
	destroyGantt()
})
</script>

<style scoped>
:deep(.bar-selected .bar) {
	stroke: #111827;
	stroke-width: 2px;
}

@media (prefers-color-scheme: dark) {
	:deep(.bar-selected .bar) {
		stroke: #f3f4f6;
	}
}

:deep(.link-from .bar) {
	stroke: #2563eb;
	stroke-width: 2px;
	stroke-dasharray: 4 2;
}

:deep(.hr-gantt-wrap .gantt .bar-label) {
	display: none;
}

.hr-gantt--link-mode .hr-gantt-body {
	cursor: crosshair;
}
</style>
