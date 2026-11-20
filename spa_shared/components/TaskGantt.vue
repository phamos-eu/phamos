<template>
	<div class="hr-gantt flex min-h-0 flex-1 flex-col bg-surface-white text-ink-gray-9 dark:bg-surface-gray-1">
		<div class="hr-gantt-main flex min-h-0 flex-1">
			<div
				class="hr-gantt-left flex flex-shrink-0 flex-col border-r border-outline-gray-2 bg-surface-white dark:bg-surface-gray-1"
				:style="{ width: `${LIST_WIDTH}px` }"
			>
				<div
					class="hr-gantt-corner flex flex-shrink-0 items-center gap-1.5 border-b border-outline-gray-2 bg-surface-gray-1 px-2 dark:bg-surface-gray-2"
					:style="{ height: `${TIMELINE_CONTROLS_HEIGHT}px` }"
				>
					<FormControl
						:model-value="search"
						type="text"
						size="sm"
						placeholder="Search…"
						class="min-w-0 flex-1"
						@update:model-value="emit('update:search', $event)"
					/>
					<InboxStatusFilter
						:model-value="includeCompleted"
						active-label="Active tasks"
						include-label="Include completed"
						aria-label="Filter tasks"
						@update:model-value="emit('update:includeCompleted', $event)"
					/>
				</div>
				<div
					class="hr-gantt-header-spacer flex-shrink-0 border-b border-outline-gray-2 bg-surface-gray-1 dark:bg-surface-gray-2"
					:style="{ height: `${HEADER_TOTAL}px` }"
				/>
				<div
					ref="listScroll"
					class="hr-gantt-list min-h-0 flex-1 overflow-y-auto overflow-x-hidden"
					@scroll="onListScroll"
				>
					<div :style="listRowsStyle">
						<button
							v-for="task in ganttTasks"
							:key="task.id"
							type="button"
							class="hr-gantt-list-row flex w-full items-center gap-2 border-b border-outline-gray-1 px-3 text-left text-xs text-ink-gray-8 hover:bg-surface-gray-2"
							:class="{
								'hr-gantt-list-row--selected': task.id === selectedName,
								'hr-gantt-list-row--group': rowMeta(task.id).is_group,
							}"
							:style="{ height: `${ROW_HEIGHT}px` }"
							@click="emit('select', task.id)"
						>
							<template v-if="rowMeta(task.id).is_group">
								<!-- Department header row of the company view (#1948): click collapses it. -->
								<FeatherIcon
									:name="rowMeta(task.id).collapsed ? 'chevron-right' : 'chevron-down'"
									class="h-3.5 w-3.5 flex-shrink-0 text-ink-gray-5"
								/>
								<span
									class="h-2.5 w-2.5 flex-shrink-0 rounded-full"
									:style="{ backgroundColor: rowMeta(task.id).color }"
								/>
								<span class="min-w-0 flex-1 truncate font-semibold">{{ task.name }}</span>
								<span class="flex-shrink-0 text-[10px] text-ink-gray-5">
									{{ rowMeta(task.id).group_count }}
								</span>
							</template>
							<span v-else class="min-w-0 flex-1 truncate font-medium">{{ task.name }}</span>
							<span
								v-if="taskStatus(task.id)"
								class="flex-shrink-0 rounded px-1.5 py-0.5 text-[10px] text-ink-gray-5"
							>
								{{ taskStatus(task.id) }}
							</span>
						</button>
					</div>
					<div v-if="undatedTasks.length" class="border-t border-outline-gray-2">
						<p
							class="px-3 py-1.5 text-[10px] font-medium uppercase tracking-wide text-ink-gray-4"
						>
							No dates
						</p>
						<button
							v-for="task in undatedTasks"
							:key="task.name"
							type="button"
							class="hr-gantt-list-row flex w-full items-center gap-2 border-b border-outline-gray-1 px-3 text-left text-xs text-ink-gray-6 hover:bg-surface-gray-2"
							:class="{ 'hr-gantt-list-row--selected': task.name === selectedName }"
							:style="{ height: `${ROW_HEIGHT}px` }"
							@click="emit('select', task.name)"
						>
							<span class="min-w-0 flex-1 truncate">{{ task.subject || task.name }}</span>
						</button>
					</div>
				</div>
				<div
					ref="listFooter"
					class="hr-gantt-list-footer flex-shrink-0 border-t border-outline-gray-2 bg-surface-gray-1 p-2 dark:bg-surface-gray-2"
				>
					<form class="flex items-center gap-1.5" @submit.prevent="openNewTaskDialog">
						<FormControl
							ref="newTaskInput"
							v-model="newTaskSubject"
							type="text"
							size="sm"
							placeholder="New task…"
							class="min-w-0 flex-1"
						/>
						<Button type="submit" variant="solid" size="sm">Add</Button>
					</form>
					<NewTaskDialog
						v-model="newTaskDialogOpen"
						:options="options"
						:initial-subject="newTaskSubject"
						@created="onNewTaskCreated"
					/>
				</div>
			</div>

			<div
				class="hr-gantt-right flex min-w-0 flex-1 flex-col"
				:class="{ 'hr-gantt--linking': drag }"
			>
				<div
					class="hr-gantt-timeline-controls flex flex-shrink-0 items-center gap-3 border-b border-outline-gray-2 bg-surface-gray-1 px-3 dark:bg-surface-gray-2"
					:style="{ height: `${TIMELINE_CONTROLS_HEIGHT}px` }"
				>
					<label class="flex items-center gap-1.5 text-[11px] text-ink-gray-5">
						<span>Start</span>
						<input
							v-model="frameStart"
							type="date"
							class="form-input h-7 rounded border border-outline-gray-2 bg-surface-gray-2 px-1.5 text-xs text-ink-gray-8"
							@change="onFrameChange"
						/>
					</label>
					<label class="flex items-center gap-1.5 text-[11px] text-ink-gray-5">
						<span>End</span>
						<input
							v-model="frameEnd"
							type="date"
							class="form-input h-7 rounded border border-outline-gray-2 bg-surface-gray-2 px-1.5 text-xs text-ink-gray-8"
							@change="onFrameChange"
						/>
					</label>
					<span
						v-if="selectionRangeLabel"
						class="text-[11px] font-medium text-ink-blue-3"
					>
						{{ selectionRangeLabel }}
					</span>
					<!-- Extra controls of the hosting view, e.g. "Own / All departments" (#1948). -->
					<slot name="toolbar" />
					<label class="ml-auto flex items-center gap-2 text-[11px] text-ink-gray-5">
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
					class="hr-gantt-header-scroll flex-shrink-0 overflow-x-auto bg-surface-gray-1 dark:bg-surface-gray-2"
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
					class="hr-gantt-body min-h-0 flex-1 overflow-auto bg-surface-white dark:bg-surface-gray-1"
					@scroll="onBodyScroll"
				>
					<div ref="bodyInner" class="hr-gantt-body-inner relative" :style="bodyInnerStyle">
						<div
							v-if="!ganttTasks.length"
							class="absolute inset-0 z-[3] flex items-center justify-center text-xs text-ink-gray-5"
						>
							Set expected dates to show tasks on the timeline
						</div>
						<div ref="ganttHost" class="hr-gantt-wrap" />

						<!-- Drag-to-link (#2001): a dot after the hovered bar; drag it onto the task that follows. -->
						<svg v-if="drag" class="hr-gantt-link-line" aria-hidden="true">
							<line :x1="drag.x0" :y1="drag.y0" :x2="drag.x" :y2="drag.y" />
						</svg>
						<button
							v-if="handle"
							type="button"
							class="hr-gantt-link-handle"
							:class="{ 'hr-gantt-link-handle--active': drag }"
							:style="{ left: `${handle.x}px`, top: `${handle.y}px` }"
							:title="__('Drag onto the task that follows')"
							:aria-label="__('Drag onto the task that follows')"
							@pointerdown="onHandlePointerDown"
							@pointermove="onHandlePointerMove"
							@pointerup="onHandlePointerUp"
							@pointercancel="endDrag"
							@mouseenter="keepHandle"
							@mouseleave="hideHandleSoon"
						/>

						<!-- Click on an arrow (#2001): who waits for whom, and remove. -->
						<div
							v-if="arrowPopover"
							ref="popoverEl"
							role="dialog"
							:aria-label="__('Dependency')"
							class="hr-gantt-dep-popover absolute z-[6] w-64 rounded-lg border border-outline-gray-2 bg-surface-white p-3 shadow-lg dark:bg-surface-gray-2"
							:style="{ left: `${arrowPopover.x}px`, top: `${arrowPopover.y}px` }"
						>
							<div class="flex items-center gap-2 text-sm font-semibold text-ink-gray-9">
								<span class="h-2 w-2 flex-shrink-0 rounded-full bg-surface-gray-5" />
								<span class="min-w-0 truncate">{{ taskTitle(arrowPopover.from) }}</span>
							</div>
							<div class="my-1 pl-4 text-xs text-ink-gray-5">{{ __("must finish before") }}</div>
							<div class="flex items-center gap-2 text-sm font-semibold text-ink-gray-9">
								<span class="h-2 w-2 flex-shrink-0 rounded-full bg-surface-gray-5" />
								<span class="min-w-0 truncate">{{ taskTitle(arrowPopover.to) }}</span>
							</div>
							<Button
								ref="popoverRemove"
								class="mt-3 w-full"
								size="sm"
								variant="outline"
								theme="red"
								@click="removeArrow"
							>
								{{ __("Remove dependency") }}
							</Button>
						</div>
					</div>
				</div>
				<div
					class="hr-gantt-footer-spacer flex-shrink-0 border-t border-outline-gray-2 bg-surface-gray-1 dark:bg-surface-gray-2"
					:style="{ height: `${listFooterHeight}px` }"
				/>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue"
import Gantt from "frappe-gantt"
import { FeatherIcon } from "frappe-ui"
import InboxStatusFilter from "@spa/components/InboxStatusFilter.vue"
import NewTaskDialog from "@spa/components/NewTaskDialog.vue"
import { formatDate, todayIsoInUserTz } from "@spa/utils/datetime"
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
import { addArrowHitAreas, restyleDependencyArrows } from "../utils/ganttDependencyArrows"
import { handlePoint, linkTargetId } from "../utils/ganttDependencyDrag"
import { __ } from "@spa/utils/i18n.js"
import { updateGanttTodayStrip } from "../utils/ganttTodayStrip"
import { updateGanttSelectedRow } from "../utils/ganttSelectedRow"
import { ganttBuildAction } from "../utils/ganttBuildAction"
import spaConfig from "@/config"

const BAR_COLOR_STYLE_ID = spaConfig.barColorStyleId || `${spaConfig.slug}-gantt-bar-colors`

const props = defineProps({
	tasks: { type: Array, default: () => [] },
	selectedName: { type: String, default: null },
	search: { type: String, default: "" },
	includeCompleted: { type: Boolean, default: false },
	// get_form_options of the cockpit, for the "New Task" dialog (#1752).
	options: { type: Object, default: () => ({}) },
})

const emit = defineEmits([
	"select",
	"date-change",
	"dependency-change",
	"dependency-remove",
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
const listFooter = ref(null)
const bodyViewportHeight = ref(0)
/** Height of the list's "new task" footer, mirrored as a spacer under the timeline
 *  so both columns have the same visible height and stay scroll-locked to the bottom. */
const listFooterHeight = ref(0)
/** Bumps periodically so the now-line tracks the clock. */
const nowTick = ref(Date.now())

let bodyResizeObserver = null
let listFooterResizeObserver = null
let nowTickTimer = null

const zoom = ref(38)
const frameStart = ref("")
const frameEnd = ref("")
const newTaskSubject = ref("")
const newTaskDialogOpen = ref(false)
/** Drag-to-link (#2001): the dot shown after a hovered bar, {id, x, y} in body-inner pixels. */
const handle = ref(null)
/** While dragging: {from, x0, y0, x, y, target}. */
const drag = ref(null)
/** The arrow clicked: {from, to, x, y}. */
const arrowPopover = ref(null)
const bodyInner = ref(null)
const popoverEl = ref(null)
const popoverRemove = ref(null)
let hideHandleTimer = null

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
			// Rows the hosting view marks read-only can't be dragged, resized or linked (#1948).
			if (t.locked || t.is_group) classes.push("bar-locked")
			if (t.is_group) classes.push("gantt-dept-header")
			if (t.empty) classes.push("gantt-dept-header-empty")
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

const bodyInnerMinHeightPx = computed(() => Math.max(bodyViewportHeight.value, 1))

/** Real row-content height for the dated tasks, shared by the list and the timeline
 *  so both scrollable columns end at the same point and stay row-locked. */
const rowsContentHeight = computed(() => LIST_TOP_OFFSET + ganttTasks.value.length * ROW_HEIGHT)

const bodyInnerStyle = computed(() => {
	const minH = bodyInnerMinHeightPx.value
	return {
		width: `${timeline.value.totalWidth}px`,
		minHeight: minH > 0 ? `${minH}px` : undefined,
	}
})

const listRowsStyle = computed(() => ({
	paddingTop: `${LIST_TOP_OFFSET}px`,
	minHeight: `${bodyInnerMinHeightPx.value}px`,
}))

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

const rowMetaMap = computed(() => Object.fromEntries(props.tasks.map((t) => [t.name, t])))

/** The row as the hosting view passed it (is_group, collapsed, group_count, locked …). */
function rowMeta(id) {
	return rowMetaMap.value[id] || {}
}

function isLocked(id) {
	const row = rowMeta(id)
	return Boolean(row.locked || row.is_group)
}

/** frappe-gantt has no read-only bars: it starts a drag on a mousedown delegated from its SVG.
 *  Stopping that mousedown on the host (capture phase) for locked bars keeps them in place,
 *  while clicks still select them. */
function onHostMouseDown(e) {
	const wrapper = e.target?.closest?.(".bar-wrapper")
	if (wrapper && isLocked(wrapper.getAttribute("data-id"))) e.stopPropagation()
}

const dependsOnMap = computed(() =>
	Object.fromEntries(ganttTasks.value.map((t) => [t.id, t.dependencies || []]))
)
const linkRows = { isLocked, dependsOn: (id) => dependsOnMap.value[id] || [] }

function taskTitle(id) {
	return rowMeta(id).subject || id
}

function innerRect() {
	return bodyInner.value?.getBoundingClientRect() || null
}

function barOf(id) {
	return gantt?.bars?.find((bar) => bar.task.id === id) || null
}

// --- Drag-to-link (#2001) --------------------------------------------------------------------

function onHostMouseOver(e) {
	if (drag.value) return
	const wrapper = e.target?.closest?.(".bar-wrapper")
	if (!wrapper) return
	const id = wrapper.getAttribute("data-id")
	if (isLocked(id)) return
	showHandle(id)
}

function onHostMouseOut(e) {
	if (drag.value) return
	const wrapper = e.target?.closest?.(".bar-wrapper")
	if (!wrapper || wrapper.contains(e.relatedTarget)) return
	hideHandleSoon()
}

function showHandle(id) {
	clearTimeout(hideHandleTimer)
	const bar = barOf(id)?.$bar
	const origin = innerRect()
	if (!bar || !origin) return
	handle.value = { id, ...handlePoint(bar.getBoundingClientRect(), origin) }
}

function keepHandle() {
	clearTimeout(hideHandleTimer)
}

function hideHandleSoon() {
	if (drag.value) return
	clearTimeout(hideHandleTimer)
	hideHandleTimer = setTimeout(() => {
		if (!drag.value) handle.value = null
	}, 300)
}

function onHandlePointerDown(e) {
	if (e.button !== 0 || !handle.value) return
	e.preventDefault()
	e.stopPropagation()
	closeArrowPopover()
	e.currentTarget?.setPointerCapture?.(e.pointerId)
	const { id, x, y } = handle.value
	drag.value = { from: id, x0: x, y0: y, x, y, target: null }
	updateBarStateClasses()
}

/** Scroll the chart while the pointer is near its edge, so far-away bars can be reached. */
function autoScroll(e) {
	const body = bodyScroll.value
	if (!body) return
	const rect = body.getBoundingClientRect()
	const edge = 32
	const step = 14
	if (e.clientY < rect.top + edge) body.scrollTop -= step
	else if (e.clientY > rect.bottom - edge) body.scrollTop += step
	if (e.clientX < rect.left + edge) body.scrollLeft -= step
	else if (e.clientX > rect.right - edge) body.scrollLeft += step
}

function onHandlePointerMove(e) {
	if (!drag.value) return
	autoScroll(e)
	const origin = innerRect()
	if (!origin) return
	drag.value.x = e.clientX - origin.left
	drag.value.y = e.clientY - origin.top
	const wrapper = document.elementFromPoint(e.clientX, e.clientY)?.closest?.(".bar-wrapper")
	const target = linkTargetId(drag.value.from, wrapper?.getAttribute("data-id") || null, linkRows)
	if (target !== drag.value.target) {
		drag.value.target = target
		updateBarStateClasses()
	}
}

function onHandlePointerUp() {
	if (!drag.value) return
	const { from, target } = drag.value
	endDrag()
	if (target) emit("dependency-change", { name: target, depends_on: from })
}

function endDrag() {
	drag.value = null
	handle.value = null
	updateBarStateClasses()
}

// --- Arrow popover (#2001) -------------------------------------------------------------------

function onHostClick(e) {
	const link = e.target?.closest?.(".dep-link")
	if (!link) return
	e.stopPropagation()
	const origin = innerRect()
	if (!origin) return
	arrowPopover.value = {
		from: link.dataset.from,
		to: link.dataset.to,
		...popoverPoint(e.clientX - origin.left, e.clientY - origin.top),
	}
	markActiveArrow()
	nextTick(() => {
		const el = popoverRemove.value?.$el || popoverRemove.value
		el?.focus?.()
	})
}

const POPOVER_WIDTH = 256
const POPOVER_HEIGHT = 130

/** Below and right of the click, flipped left or up where it would leave the visible chart. */
function popoverPoint(x, y) {
	const body = bodyScroll.value
	const right = body ? body.scrollLeft + body.clientWidth : Infinity
	const bottom = body ? body.scrollTop + body.clientHeight : Infinity
	return {
		x: x + 8 + POPOVER_WIDTH > right ? Math.max(0, x - 8 - POPOVER_WIDTH) : x + 8,
		y: y + 8 + POPOVER_HEIGHT > bottom ? Math.max(0, y - 8 - POPOVER_HEIGHT) : y + 8,
	}
}

function closeArrowPopover() {
	if (!arrowPopover.value) return
	arrowPopover.value = null
	markActiveArrow()
}

function onDocumentPointerDown(e) {
	if (!arrowPopover.value) return
	if (popoverEl.value?.contains(e.target)) return
	if (e.target?.closest?.(".dep-link")) return
	closeArrowPopover()
}

function removeArrow() {
	const popover = arrowPopover.value
	if (!popover) return
	closeArrowPopover()
	emit("dependency-remove", { name: popover.to, depends_on: popover.from })
}

function markActiveArrow() {
	const svg = ganttHost.value
	if (!svg) return
	const active = arrowPopover.value
	for (const link of svg.querySelectorAll(".dep-link")) {
		link.classList.toggle(
			"dep-link--active",
			Boolean(active && link.dataset.from === active.from && link.dataset.to === active.to)
		)
	}
}

function onKeyDown(e) {
	if (e.key !== "Escape") return
	if (drag.value) endDrag()
	else closeArrowPopover()
}

function focusNewTaskInput() {
	const el = newTaskInput.value
	const input = el?.$el?.querySelector?.("input") || el?.$el || el
	input?.focus?.()
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
	if (e.button !== 0) return
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

function todayDate() {
	const iso = todayIsoInUserTz()
	const [y, mo, dd] = iso.split("-").map(Number)
	return new Date(y, mo - 1, dd, 0, 0, 0, 0)
}

// "New task…" only takes the subject; the dialog asks for the rest (#1752).
function openNewTaskDialog() {
	newTaskDialogOpen.value = true
}

function onNewTaskCreated(task) {
	newTaskSubject.value = ""
	emit("created", task.name)
	nextTick(focusNewTaskInput)
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

/** frappe-gantt pads its own SVG height ~100px beyond the real rows, which would let
 *  the timeline scroll further than the task list. Clip it to our own row formula so
 *  both columns have the same scrollable height and stay locked row-for-row. */
function fixSvgHeight() {
	if (!gantt) return
	const svg = ganttHost.value?.querySelector("svg.gantt")
	if (svg) svg.setAttribute("height", String(rowsContentHeight.value))
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
	fixSvgHeight()
	updateBarStateClasses()
	restyleDependencyArrows(gantt)
	addArrowHitAreas(gantt)
	// The bars moved or were redrawn: a dot or popover from before would point at nothing.
	if (!drag.value) handle.value = null
	arrowPopover.value = null
	updateTodayStripOverlay()
}

function buildGantt() {
	const tasksForGantt = ganttTasks.value
	injectBarColors()

	const action = ganttBuildAction(Boolean(gantt), tasksForGantt.length)
	if (action === "clear") {
		destroyGantt()
		return
	}

	if (action === "create") {
		if (!ganttHost.value) return
		gantt = new Gantt(ganttHost.value, tasksForGantt, {
			view_mode: "Day",
			column_width: zoom.value,
			bar_height: BAR_HEIGHT,
			padding: ROW_PADDING,
			header_height: 0,
			date_format: "YYYY-MM-DD",
			language: "en",
			on_click: (task) => emit("select", task.id),
			on_date_change: (task, start, end) => {
				// A locked bar only moves along with a predecessor it depends on: redraw, don't save.
				if (isLocked(task.id)) {
					applyGanttFrame()
					return
				}
				emit("date-change", {
					name: task.id,
					exp_start_date: formatDateIso(start),
					exp_end_date: formatDateIso(end),
				})
			},
		})
	} else {
		// Update the existing chart in place rather than tearing down and
		// reconstructing the SVG on every edit: that caused every bar to visibly
		// flash and reset the timeline's scroll position back to the top.
		// setup_tasks() absorbs the new data without touching gantt_start/gantt_end,
		// so applyGanttFrame() below still re-applies our own custom date range.
		gantt.setup_tasks(tasksForGantt)
	}

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
		bar.group.classList.toggle("bar-selected", selected)
		bar.group.classList.toggle("link-source", bar.task.id === drag.value?.from)
		bar.group.classList.toggle("link-target", bar.task.id === drag.value?.target)
	}
	updateGanttSelectedRow(gantt, props.selectedName)
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

/** Mirrors onHeaderScroll/onBodyScroll: syncs the timeline to the list on any native
 *  scroll of the list (wheel, touch, keyboard) — not just mouse-wheel deltas. */
function onListScroll() {
	if (syncingScroll) return
	syncingScroll = true
	if (bodyScroll.value && listScroll.value) {
		bodyScroll.value.scrollTop = listScroll.value.scrollTop
	}
	syncingScroll = false
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


onMounted(() => {
	initFrame()
	document.addEventListener("keydown", onKeyDown)
	document.addEventListener("pointerdown", onDocumentPointerDown, true)
	ganttHost.value?.addEventListener("mousedown", onHostMouseDown, true)
	ganttHost.value?.addEventListener("mouseover", onHostMouseOver)
	ganttHost.value?.addEventListener("mouseout", onHostMouseOut)
	ganttHost.value?.addEventListener("click", onHostClick, true)
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
		if (listFooter.value) {
			listFooterHeight.value = listFooter.value.offsetHeight
			listFooterResizeObserver = new ResizeObserver(() => {
				listFooterHeight.value = listFooter.value?.offsetHeight || 0
			})
			listFooterResizeObserver.observe(listFooter.value)
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
	listFooterResizeObserver?.disconnect()
	listFooterResizeObserver = null
	clearTimeout(hideHandleTimer)
	document.removeEventListener("keydown", onKeyDown)
	document.removeEventListener("pointerdown", onDocumentPointerDown, true)
	ganttHost.value?.removeEventListener("mousedown", onHostMouseDown, true)
	ganttHost.value?.removeEventListener("mouseover", onHostMouseOver)
	ganttHost.value?.removeEventListener("mouseout", onHostMouseOut)
	ganttHost.value?.removeEventListener("click", onHostClick, true)
	bodyScroll.value?.removeEventListener("wheel", onWheel)
	document.getElementById(BAR_COLOR_STYLE_ID)?.remove()
	destroyGantt()
})
</script>

<style scoped>
:deep(.bar-selected .bar) {
	stroke: var(--ink-blue-3);
	stroke-width: 2.5px;
	filter: brightness(1.08);
}

:deep(.bar-selected .bar-progress) {
	filter: brightness(1.08);
}

:deep(.link-source .bar),
:deep(.link-target .bar) {
	stroke: var(--ink-blue-3);
	stroke-width: 2.5px;
}

:deep(.link-source .bar) {
	stroke-dasharray: 4 2;
}

/* Drag-to-link (#2001) */
.hr-gantt-link-handle {
	position: absolute;
	z-index: 5;
	width: 12px;
	height: 12px;
	margin: -6px 0 0 -6px;
	border: 2px solid var(--ink-blue-3);
	border-radius: 9999px;
	background: var(--surface-white);
	cursor: crosshair;
	touch-action: none;
}

.hr-gantt-link-handle:hover,
.hr-gantt-link-handle--active,
.hr-gantt-link-handle:focus-visible {
	background: var(--ink-blue-3);
	outline: none;
}

.hr-gantt-link-line {
	position: absolute;
	inset: 0;
	z-index: 4;
	width: 100%;
	height: 100%;
	overflow: visible;
	pointer-events: none;
}

.hr-gantt-link-line line {
	stroke: var(--ink-blue-3);
	stroke-width: 2px;
}

/* Clickable arrows: a wide invisible stroke on top of each arrow. */
:deep(.dep-hit) {
	fill: none;
	stroke: transparent;
	stroke-width: 12px;
	pointer-events: stroke;
	cursor: pointer;
}

:deep(.dep-link:hover path:first-child),
:deep(.dep-link--active path:first-child) {
	stroke: var(--ink-gray-9);
	stroke-width: 2.4px;
}

:deep(.hr-gantt-wrap .gantt .bar-label) {
	display: none;
}

.hr-gantt-list {
	scrollbar-width: none;
	-ms-overflow-style: none;
}

.hr-gantt-list::-webkit-scrollbar {
	display: none;
}

.hr-gantt--linking .hr-gantt-body {
	cursor: crosshair;
	user-select: none;
}

/* Read-only rows of the company view (#1948): no resize or progress handles. */
:deep(.bar-locked .handle) {
	display: none;
}

:deep(.bar-locked) {
	cursor: pointer;
}

/* Department header row: a thin summary bar over the department's span. */
:deep(.gantt-dept-header .bar) {
	transform: scaleY(0.35);
	transform-box: fill-box;
	transform-origin: center;
}

:deep(.gantt-dept-header .bar-progress) {
	display: none;
}

:deep(.gantt-dept-header-empty) {
	display: none;
}

.hr-gantt-list-row--group {
	background-color: var(--surface-gray-1);
}
</style>
