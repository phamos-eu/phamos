<template>
	<!-- Read-only roadmap timeline (#2034), drawn by Vue from plain data (no frappe-gantt):
	     one row per module, chapters as level-step bars, features as dots, dependency arrows,
	     markers, baseline bars and the today line. Fills the height it is given and scrolls
	     inside (sideways, and down when the rows don't fit); the page never scrolls.
	     Keyboard: Tab and the arrow keys move between bars and dots, Enter selects, Esc clears. -->
	<div class="roadmap-gantt" role="region" :aria-label="__('Roadmap')" @keydown="onKeydown">
		<div ref="scroller" class="roadmap-gantt__scroll">
			<div
				class="roadmap-gantt__grid"
				:style="{
					width: `${labelWidth + timeline.totalWidth}px`,
					gridTemplateColumns: `${labelWidth}px ${timeline.totalWidth}px`,
				}"
			>
				<div class="roadmap-gantt__corner">
					<slot name="corner" />
				</div>
				<div class="roadmap-gantt__header">
					<RoadmapHeader :timeline="timeline" :zoom="zoom" :today="today" />
				</div>
				<div class="roadmap-gantt__labels">
					<div :style="{ height: `${MARKER_STRIP}px` }" />
					<RoadmapRowList :rows="rows" :layout="rowLayout" />
				</div>

				<div class="roadmap-gantt__body" :style="{ height: `${bodyHeight}px` }" @click="onBodyClick">
					<div
						v-for="row in rowLayout"
						:key="`bg-${row.name}`"
						class="roadmap-gantt__row-line"
						:style="{ top: `${MARKER_STRIP + row.top + row.height - 1}px` }"
					/>
					<div
						v-for="month in timeline.months.slice(1)"
						:key="`m-${month.key}`"
						class="roadmap-gantt__month-line"
						:style="{ left: `${month.left}px` }"
					/>
					<div
						v-if="today"
						class="hr-gantt-today-strip"
						:style="{ left: `${today.left}px`, width: `${today.width}px` }"
					/>
					<div v-if="today" class="hr-gantt-today-strip-edge" :style="{ left: `${today.edgeLeft}px` }" />

					<MarkerLayer :markers="markers" :timeline="timeline" :height="bodyHeight" />

					<svg
						class="roadmap-gantt__arrows"
						:width="timeline.totalWidth"
						:height="bodyHeight"
						aria-hidden="true"
					>
						<path
							v-for="arrow in arrows"
							:key="`${arrow.from}>${arrow.to}`"
							:d="arrow.d"
							class="roadmap-gantt__arrow"
							:class="{
								'roadmap-gantt__arrow--conflict': arrow.conflict,
								'roadmap-gantt__arrow--critical': arrow.critical,
							}"
						/>
					</svg>

					<template v-if="showBaseline">
						<BaselineBar
							v-for="item in baselineBars"
							:key="`base-${item.name}`"
							:baseline="item.baseline"
							:rect="item.rect"
						/>
					</template>

					<SlackLabel
						v-for="item in slackLabels"
						:key="`slack-${item.name}`"
						:slack-days="item.bar.slackDays ?? null"
						:shift-days="item.bar.shiftDays ?? null"
						:left="item.left"
						:top="item.top"
						:inside="item.inside"
					/>
					<!-- Row by row, left to right, so Tab follows the same order as the arrow keys. -->
					<template v-for="item in navOrder" :key="item.key">
						<LevelBar
							v-if="item.type === 'bar'"
							:bar="item.bar"
							:rect="item.rect"
							:selected="isSelected('bar', item.name)"
							:data-nav-key="item.key"
						/>
						<EventDot
							v-else
							:stack="item.stack"
							:top="item.top"
							:selected="item.stack.events.some((e) => isSelected('event', e.name))"
							:data-nav-key="item.key"
						/>
					</template>

					<div v-if="!rows.length" class="roadmap-gantt__empty">
						{{ __("Nothing planned yet") }}
					</div>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue"
import { __ } from "@spa/utils/i18n.js"
import { todayIsoInUserTz } from "@spa/utils/datetime.js"
import { defaultFrameRange, scrollLeftForDate, todayStripRect } from "@spa/utils/ganttTimeline.js"
import {
	barRect,
	dependencyPaths,
	EVENT_STRIP,
	fillRange,
	LANE_HEIGHT,
	roadmapTimeline,
	ROW_PADDING,
	rowHeights,
	stackEvents,
	stackSelection,
	toDay,
	ZOOM_DAY_WIDTH,
} from "@spa/utils/roadmapLayout.js"
import RoadmapHeader from "./roadmap/RoadmapHeader.vue"
import RoadmapRowList from "./roadmap/RoadmapRowList.vue"
import LevelBar from "./roadmap/LevelBar.vue"
import BaselineBar from "./roadmap/BaselineBar.vue"
import EventDot from "./roadmap/EventDot.vue"
import MarkerLayer from "./roadmap/MarkerLayer.vue"
import SlackLabel from "./roadmap/SlackLabel.vue"

const props = defineProps({
	/**
	 * One row per module: [{ name, label, sublabel?, bars, events }]
	 * bar: { name, label, start, end, fromLevel, toLevel, currentLevel, critical, faded,
	 *        slackDays, shiftDays, baseline: { start, end } | null }
	 * event: { name, label, date, status: "planned" | "finished" }
	 * Dates are "YYYY-MM-DD" strings or Dates; bar names are unique across rows.
	 */
	rows: { type: Array, default: () => [] },
	/** [{ from, to, conflict }]: bar names; red when `conflict` */
	dependencies: { type: Array, default: () => [] },
	/** [{ name, type: "milestone" | "release", title, date, url?, late? }]: see MarkerLayer */
	markers: { type: Array, default: () => [] },
	/** { start, end }: the visible date range; three months from this month when empty */
	range: { type: Object, default: null },
	zoom: { type: String, default: "month", validator: (v) => ["week", "month", "quarter"].includes(v) },
	showBaseline: { type: Boolean, default: false },
	/** { type: "bar" | "event", name } or null; a stack is selected when it holds `name` */
	selected: { type: Object, default: null },
	/** width in px of the row-label column */
	labelWidth: { type: Number, default: 168 },
})

/**
 * select: { type: "bar", name }, { type: "event", name } for one feature, or
 * { type: "event", name, names } for a stack of several features (names in date order);
 * null on Esc.
 */
const emit = defineEmits(["select"])

// Strip at the top of the body that holds the marker diamonds.
const MARKER_STRIP = 14
const BAR_HEIGHT = 14
// Bar sits 2 px into its lane; the baseline bar 1 px below the bar.
const BAR_OFFSET = 2
// Dots closer than this stack into one; a stack pill is about 16 px wide.
const DOT_GAP = 18
// Gap after a bar that "+5 d  3 d late" needs; with less, the label goes inside the bar.
const SLACK_ROOM = 72
// Room for the "Nothing planned yet" line when there are no rows.
const EMPTY_HEIGHT = 80

const scroller = ref(null)
// Width of the chart area (scroll box minus the label column), kept up to date on resize.
const chartWidth = ref(0)

const timeline = computed(() => {
	const range = props.range?.start && props.range?.end ? props.range : defaultFrameRange()
	return roadmapTimeline(fillRange(range, props.zoom, chartWidth.value), props.zoom)
})

const today = computed(() => todayStripRect(timeline.value))

const rowLayout = computed(() => rowHeights(props.rows))

const bodyHeight = computed(() => {
	const last = rowLayout.value[rowLayout.value.length - 1]
	return MARKER_STRIP + (last ? last.top + last.height : EMPTY_HEIGHT)
})

const placedBars = computed(() => {
	const out = []
	props.rows.forEach((row, rowIndex) => {
		const layout = rowLayout.value[rowIndex]
		for (const bar of row.bars || []) {
			const rect = barRect(timeline.value, bar.start, bar.end)
			if (!rect) continue
			const lane = layout.barLanes[bar.name] ?? 0
			const top = MARKER_STRIP + layout.top + ROW_PADDING + EVENT_STRIP + lane * LANE_HEIGHT + BAR_OFFSET
			out.push({
				key: `bar:${bar.name}`,
				type: "bar",
				name: bar.name,
				rowIndex,
				x: rect.left,
				bar,
				rect: { ...rect, top, height: BAR_HEIGHT },
			})
		}
	})
	return out
})

const baselineBars = computed(() => {
	const out = []
	for (const item of placedBars.value) {
		const baseline = item.bar.baseline
		if (!baseline?.start || !baseline?.end) continue
		const rect = barRect(timeline.value, baseline.start, baseline.end)
		if (!rect) continue
		out.push({ name: item.name, baseline, rect: { ...rect, top: item.rect.top + BAR_HEIGHT + 1 } })
	}
	return out
})

/** Slack and shift after each bar; inside its right end when the next bar of the lane is too close. */
const slackLabels = computed(() => {
	const byLane = new Map()
	for (const item of placedBars.value) {
		const lane = `${item.rowIndex}:${item.rect.top}`
		if (!byLane.has(lane)) byLane.set(lane, [])
		byLane.get(lane).push(item)
	}
	const out = []
	for (const items of byLane.values()) {
		items.sort((a, b) => a.rect.left - b.rect.left)
		items.forEach((item, idx) => {
			const end = item.rect.left + item.rect.width
			const next = items[idx + 1]
			const inside = Boolean(next && next.rect.left - end < SLACK_ROOM)
			out.push({
				name: item.name,
				bar: item.bar,
				inside,
				left: inside ? end - 3 : end + 4,
				top: item.rect.top + item.rect.height / 2,
			})
		})
	}
	return out
})

const placedEvents = computed(() => {
	const out = []
	props.rows.forEach((row, rowIndex) => {
		const layout = rowLayout.value[rowIndex]
		const top = MARKER_STRIP + layout.top + ROW_PADDING + EVENT_STRIP / 2
		for (const stack of stackEvents(row.events, timeline.value, DOT_GAP)) {
			out.push({ key: `event:${rowIndex}:${stack.key}`, type: "event", name: stack.name, rowIndex, x: stack.x, stack, top })
		}
	})
	return out
})

const arrows = computed(() => {
	const bars = {}
	for (const item of placedBars.value) {
		bars[item.name] = { ...item.rect, critical: Boolean(item.bar.critical) }
	}
	return dependencyPaths(bars, props.dependencies)
})

function isSelected(type, name) {
	return props.selected?.type === type && props.selected?.name === name
}

// --- Keyboard path and clicks ---------------------------------------------------------------

/** Bars and dots per row, left to right: the order of the arrow keys. */
const navRows = computed(() => {
	const rowsOut = props.rows.map(() => [])
	for (const item of [...placedBars.value, ...placedEvents.value]) rowsOut[item.rowIndex].push(item)
	for (const items of rowsOut) items.sort((a, b) => a.x - b.x || (a.type === b.type ? 0 : a.type === "event" ? -1 : 1))
	return rowsOut
})

const navOrder = computed(() => navRows.value.flat())

const navItems = computed(() => new Map(navOrder.value.map((item) => [item.key, item])))

function focusItem(item) {
	if (!item) return
	const el = scroller.value?.querySelector(`[data-nav-key="${CSS.escape(item.key)}"]`)
	el?.focus()
	el?.scrollIntoView?.({ block: "nearest", inline: "nearest" })
}

function neighbour(item, key) {
	const row = navRows.value[item.rowIndex]
	const pos = row.indexOf(item)
	if (key === "ArrowLeft") return row[pos - 1]
	if (key === "ArrowRight") return row[pos + 1]
	const step = key === "ArrowUp" ? -1 : 1
	for (let r = item.rowIndex + step; r >= 0 && r < navRows.value.length; r += step) {
		const candidates = navRows.value[r]
		if (!candidates.length) continue
		return candidates.reduce((best, c) => (Math.abs(c.x - item.x) < Math.abs(best.x - item.x) ? c : best))
	}
	return null
}

function selectItem(item) {
	emit("select", item.type === "event" ? stackSelection(item.stack) : { type: item.type, name: item.name })
}

function onKeydown(event) {
	if (event.key === "Escape") {
		if (props.selected) {
			event.stopPropagation()
			emit("select", null)
		}
		return
	}
	const key = event.target?.closest?.("[data-nav-key]")?.dataset.navKey
	const item = key && navItems.value.get(key)
	if (!item) return
	if (event.key === "Enter" || event.key === " ") {
		event.preventDefault()
		selectItem(item)
	} else if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
		event.preventDefault()
		focusItem(neighbour(item, event.key))
	}
}

function onBodyClick(event) {
	const key = event.target?.closest?.("[data-nav-key]")?.dataset.navKey
	const item = key && navItems.value.get(key)
	if (item) selectItem(item)
}

// --- Scrolling ------------------------------------------------------------------------------

function chartViewportWidth() {
	return Math.max(0, (scroller.value?.clientWidth || 0) - props.labelWidth)
}

function scrollToDate(date) {
	if (!scroller.value) return
	scroller.value.scrollLeft = scrollLeftForDate(timeline.value, date, chartViewportWidth())
}

function scrollToToday() {
	const day = toDay(todayIsoInUserTz())
	const tl = timeline.value
	if (day && tl.rangeStart && day >= tl.rangeStart && day < tl.rangeEnd) scrollToDate(day)
}

/**
 * Brings the selected bar or dot into view when it lies outside, for example after a side
 * panel narrowed the chart or a link in the panel selected a bar further away (#2035).
 */
function scrollSelectedIntoView() {
	const sel = props.selected
	const item = sel && navOrder.value.find((i) => (i.type === "bar" ? sel.type === "bar" && i.name === sel.name : sel.type === "event" && i.stack.events.some((e) => e.name === sel.name)))
	const el = item && scroller.value?.querySelector(`[data-nav-key="${CSS.escape(item.key)}"]`)
	if (!el) return
	const box = scroller.value.getBoundingClientRect()
	const rect = el.getBoundingClientRect()
	const viewLeft = box.left + props.labelWidth
	const viewWidth = box.right - viewLeft
	if (rect.left >= viewLeft && rect.right <= box.right) return
	// a bar wider than the view shows its start; anything else goes to the middle
	const delta = rect.width > viewWidth ? rect.left - viewLeft - 16 : rect.left + rect.width / 2 - (viewLeft + viewWidth / 2)
	scroller.value.scrollLeft += delta
}

// After the parent has drawn its side panel, so the measured width is the new one.
watch(
	() => props.selected,
	(sel) => sel && nextTick(() => requestAnimationFrame(scrollSelectedIntoView))
)

let resizeObserver = null

onMounted(() => {
	chartWidth.value = chartViewportWidth()
	// Test DOMs (jsdom, happy-dom) have no ResizeObserver; the width then stays as measured here.
	if (typeof ResizeObserver !== "undefined" && scroller.value) {
		resizeObserver = new ResizeObserver(() => {
			chartWidth.value = chartViewportWidth()
		})
		resizeObserver.observe(scroller.value)
	}
	nextTick(scrollToToday)
})

onUnmounted(() => {
	resizeObserver?.disconnect()
	resizeObserver = null
})

// Keep the date in the middle of the view when the zoom changes.
watch(
	() => props.zoom,
	(zoom, oldZoom) => {
		const tl = timeline.value
		if (!scroller.value || !tl.rangeStart) return
		const oldWidth = ZOOM_DAY_WIDTH[oldZoom] || ZOOM_DAY_WIDTH.month
		const days = Math.floor((scroller.value.scrollLeft + chartViewportWidth() / 2) / oldWidth)
		const centre = new Date(tl.rangeStart)
		centre.setDate(centre.getDate() + days)
		nextTick(() => scrollToDate(centre))
	}
)
</script>

<style scoped>
.roadmap-gantt {
	display: flex;
	height: 100%;
	min-height: 0;
	flex-direction: column;
	background: var(--surface-white);
}

.roadmap-gantt__scroll {
	position: relative;
	min-height: 0;
	flex: 1;
	overflow: auto;
	overscroll-behavior: contain;
}

.roadmap-gantt__grid {
	display: grid;
	grid-template-rows: auto auto;
}

.roadmap-gantt__corner,
.roadmap-gantt__header,
.roadmap-gantt__labels {
	position: sticky;
	background: var(--surface-gray-1);
}

.roadmap-gantt__corner {
	top: 0;
	left: 0;
	z-index: 6;
	border-right: 1px solid var(--outline-gray-2);
	border-bottom: 1px solid var(--outline-gray-2);
}

.roadmap-gantt__header {
	top: 0;
	z-index: 5;
}

.roadmap-gantt__labels {
	left: 0;
	z-index: 4;
	border-right: 1px solid var(--outline-gray-2);
	background: var(--surface-white);
}

.roadmap-gantt__body {
	position: relative;
	overflow: hidden;
	/* its own stacking context: bars, dots and slack labels stay under the sticky header and labels */
	isolation: isolate;
}

.roadmap-gantt__row-line {
	position: absolute;
	left: 0;
	right: 0;
	height: 1px;
	background: var(--outline-gray-1);
}

.roadmap-gantt__month-line {
	position: absolute;
	top: 0;
	bottom: 0;
	width: 1px;
	background: var(--outline-gray-1);
}

.roadmap-gantt__arrows {
	position: absolute;
	top: 0;
	left: 0;
	overflow: visible;
	pointer-events: none;
	z-index: 2;
}

.roadmap-gantt__arrow {
	fill: none;
	stroke: var(--ink-gray-4);
	stroke-width: 1.2;
	stroke-linecap: round;
	stroke-linejoin: round;
}

.roadmap-gantt__arrow--critical {
	stroke: var(--ink-gray-7);
	stroke-width: 2;
}

.roadmap-gantt__arrow--conflict {
	stroke: var(--ink-red-3);
}

.roadmap-gantt__empty {
	position: absolute;
	inset: 0;
	display: flex;
	align-items: center;
	justify-content: center;
	color: var(--ink-gray-5);
	font-size: 12px;
}

.roadmap-gantt__body :deep(.roadmap-level-bar),
.roadmap-gantt__body :deep(.roadmap-event) {
	z-index: 3;
}
</style>
