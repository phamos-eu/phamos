<template>
	<!--
		The meeting view as tiles (#2091), the same tiling as the cockpits' record pages (#1915,
		spa_shared/panels/tiling.js): a tree of splits that always fills the room. Every line between
		two tiles drags (double-click evens it out); a tile's title bar drags it onto another tile or
		an edge of the room, with a preview where it lands. Each tile glows in the space's colour.

		The tiles are frames only: the call, the chat and the map lie over their bodies (the page
		reports them up as `rects`), because moving the call's frame in the page would restart it.
	-->
	<div ref="area" class="pointer-events-none absolute inset-0" data-testid="meeting-tiles">
		<template v-if="room.w">
			<section
				v-for="tile in geometry.tiles"
				:key="tile.id"
				class="meeting-tile pointer-events-none absolute flex flex-col rounded-xl"
				:style="{ ...box(tile), '--area-h': hue ?? 220 }"
				role="region"
				:aria-label="titleOf(tile.id)"
				:data-testid="`meeting-tile-${tile.id}`"
			>
				<header
					class="pointer-events-auto flex h-7 flex-none cursor-grab touch-none select-none items-center gap-1.5 pl-2.5 pr-1"
					:title="__('Drag to move')"
					@pointerdown="(e) => startMove(tile.id, e)"
					@pointermove="onMove"
					@pointerup="endMove"
					@pointercancel="cancelMove"
					@lostpointercapture="cancelMove"
				>
					<FeatherIcon :name="PIECES[tile.id].icon" class="h-3.5 w-3.5 flex-shrink-0 text-ink-gray-6" />
					<span class="flex-shrink-0 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-7">
						{{ titleOf(tile.id) }}
					</span>
					<div class="ml-auto flex flex-shrink-0 items-center gap-0.5" @pointerdown.stop>
						<button
							v-if="tile.id !== biggest"
							type="button"
							class="meeting-tile__button"
							:title="__('Make it the big tile')"
							:data-testid="`meeting-tile-big-${tile.id}`"
							@click="makeBig(tile.id)"
						>
							<FeatherIcon name="maximize-2" class="h-3.5 w-3.5" />
						</button>
						<Dropdown :options="moveOptions(tile.id)" placement="right">
							<button type="button" class="meeting-tile__button" :title="__('Move to…')" :aria-label="__('Move to…')">
								<FeatherIcon name="move" class="h-3.5 w-3.5" />
							</button>
						</Dropdown>
					</div>
				</header>
				<!-- The piece lies here (the page positions it over this body). -->
				<div class="min-h-0 flex-1" :data-tile-body="tile.id" />
			</section>

			<div
				v-for="(gutter, i) in geometry.gutters"
				:key="`g${i}-${gutter.path.join('.')}-${gutter.index}`"
				role="separator"
				tabindex="0"
				:aria-orientation="gutter.axis === 'w' ? 'vertical' : 'horizontal'"
				:aria-label="__('Resize the panels')"
				:title="__('Drag to resize, double-click to even out')"
				class="group pointer-events-auto absolute z-[2] flex touch-none items-center justify-center focus:outline-none"
				:class="gutter.axis === 'w' ? 'cursor-col-resize' : 'cursor-row-resize'"
				:style="box(grabArea(gutter))"
				data-testid="meeting-tile-gutter"
				@pointerdown="(e) => startDrag(gutter, e)"
				@pointermove="onDrag"
				@pointerup="endDrag"
				@pointercancel="endDrag"
				@lostpointercapture="endDrag"
				@dblclick="even(gutter)"
				@keydown.left.prevent="gutter.axis === 'w' && nudge(gutter, -16)"
				@keydown.right.prevent="gutter.axis === 'w' && nudge(gutter, 16)"
				@keydown.up.prevent="gutter.axis === 'h' && nudge(gutter, -16)"
				@keydown.down.prevent="gutter.axis === 'h' && nudge(gutter, 16)"
			>
				<span
					class="pointer-events-none rounded-full"
					:class="[
						gutter.axis === 'w' ? 'h-full w-1' : 'h-1 w-full',
						gutterKey(gutter) === draggingKey
							? 'bg-outline-gray-4'
							: 'bg-transparent group-hover:bg-outline-gray-3 group-focus-visible:bg-outline-gray-4',
					]"
				/>
			</div>

			<!-- Where a dragged tile will land -->
			<div
				v-if="moving?.active && preview"
				class="pointer-events-none absolute z-[70] rounded-xl border-2 border-blue-500 bg-blue-500/20 transition-all duration-75"
				:style="box(preview)"
				data-testid="meeting-tile-preview"
			/>
		</template>
	</div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from "vue"
import { Dropdown, FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import {
	GUTTER,
	PAGE_EDGE_SHARE,
	clone,
	dropAt,
	dropped,
	evenAt,
	layout as computeLayout,
	normalize,
	resizeAt,
	resolve,
	sanitize,
	splitAt,
	swap,
	withAll,
} from "@spa/panels/tiling.js"

const props = defineProps({
	/** The space's colour (a hue): every tile glows in it. */
	hue: { type: [Number, String], default: null },
})
const emit = defineEmits(["rects"])

const PIECES = {
	video: { title: "Video", icon: "video", min: { w: 240, h: 180 } },
	chat: { title: "Chat", icon: "message-square", min: { w: 220, h: 200 } },
	map: { title: "Map", icon: "map", min: { w: 200, h: 140 } },
}
const IDS = Object.keys(PIECES)
const MINS = Object.fromEntries(IDS.map((id) => [id, PIECES[id].min]))
const titleOf = (id) => __(PIECES[id]?.title || id)

// Per person, in this browser (PM, 2026-11-22).
const STORE_KEY = "phamos_ophice_meeting_tiles"
function defaultTree(width) {
	const left = Math.max(260, Math.min(440, width * 0.3))
	return {
		split: "row",
		sizes: normalize([left, Math.max(400, width - left - GUTTER)]),
		children: [
			{ split: "column", sizes: [0.6, 0.4], children: [{ panel: "chat" }, { panel: "map" }] },
			{ panel: "video" },
		],
	}
}
function readStored() {
	try {
		return sanitize(JSON.parse(localStorage.getItem(STORE_KEY) || "null"))
	} catch {
		return null
	}
}
const storedTree = shallowRef(readStored())
function save(tree) {
	storedTree.value = clone(tree)
	try {
		localStorage.setItem(STORE_KEY, JSON.stringify(storedTree.value))
	} catch {
		// private window: lasts until the reload
	}
}
function reset() {
	storedTree.value = null
	try {
		localStorage.removeItem(STORE_KEY)
	} catch {
		// nothing stored
	}
}

// The room, followed as the window or the page around it changes.
const area = ref(null)
const room = reactive({ w: 0, h: 0 })
let observer = null
onMounted(() => {
	const rect = area.value.getBoundingClientRect()
	room.w = Math.floor(rect.width)
	room.h = Math.floor(rect.height)
	observer = new ResizeObserver(([entry]) => {
		room.w = Math.floor(entry.contentRect.width)
		room.h = Math.floor(entry.contentRect.height)
	})
	observer.observe(area.value)
	window.addEventListener("resize", report)
})
onBeforeUnmount(() => {
	observer?.disconnect()
	window.removeEventListener("resize", report)
	if (dragStart || moving.value?.active) passThrough(false)
	window.removeEventListener("keydown", onMoveKey)
})

const shown = new Set(IDS)
const baseTree = computed(() => withAll(storedTree.value || defaultTree(room.w || 1200), IDS, {}))
const dragTree = shallowRef(null)
const tree = computed(() => dragTree.value || baseTree.value)
const resolved = computed(() => resolve(tree.value, shown))
const geometry = computed(() =>
	room.w && resolved.value ? computeLayout(resolved.value, { x: 0, y: 0, w: room.w, h: room.h }, MINS) : { tiles: [], gutters: [] }
)
const biggest = computed(() => {
	let best = null
	for (const t of geometry.value.tiles) if (!best || t.w * t.h > best.w * best.h) best = t
	return best?.id || ""
})

const box = (r) => ({ left: `${r.x}px`, top: `${r.y}px`, width: `${r.w}px`, height: `${r.h}px` })
const GRAB = 4
const grabArea = (g) => (g.axis === "w" ? { ...g, x: g.x - GRAB, w: g.w + 2 * GRAB } : { ...g, y: g.y - GRAB, h: g.h + 2 * GRAB })

// --- The pieces' places: each tile's body in window px (the call and the chat are fixed there).
const HEADER = 28
function report() {
	const rect = area.value?.getBoundingClientRect()
	if (!rect) return
	const rects = {}
	for (const t of geometry.value.tiles) {
		rects[t.id] = { left: rect.left + t.x, top: rect.top + t.y + HEADER, width: t.w, height: Math.max(0, t.h - HEADER) }
	}
	emit("rects", rects)
}
watch(geometry, () => nextTick(report), { immediate: true })

/** Into the big tile: swap places with the largest one. */
function makeBig(id) {
	if (!biggest.value || biggest.value === id) return
	save(swap(clone(baseTree.value), id, biggest.value))
}

// --- Splitters (as in PanelLayout.vue)
const dragging = shallowRef(null)
let dragStart = null
const gutterKey = (g) => `${g.path.join(".")}:${g.index}`
const draggingKey = computed(() => (dragging.value ? gutterKey(dragging.value) : null))
const at = (axis, event) => (axis === "w" ? event.clientX : event.clientY)
const buttonDown = (event) => (event.buttons & 1) === 1

// While dragging, the call's frame must not swallow the pointer.
function passThrough(on) {
	document.documentElement.classList.toggle("meeting-tiles--dragging", on)
}

function resized(gutter, delta, base = baseTree.value) {
	const next = clone(base)
	const node = splitAt(resolve(next, shown), gutter.path)
	if (!node?.src) return null
	resizeAt(node, gutter.index, delta, gutter.avail, MINS)
	return next
}
function startDrag(gutter, event) {
	dragging.value = gutter
	dragStart = { pos: at(gutter.axis, event), base: clone(baseTree.value) }
	event.currentTarget.setPointerCapture(event.pointerId)
	passThrough(true)
}
function onDrag(event) {
	if (!dragStart) return
	if (!buttonDown(event)) return endDrag()
	dragTree.value = resized(dragging.value, at(dragging.value.axis, event) - dragStart.pos, dragStart.base)
}
function endDrag() {
	if (!dragStart) return
	passThrough(false)
	if (dragTree.value) save(dragTree.value)
	dragTree.value = null
	dragging.value = null
	dragStart = null
}
function nudge(gutter, delta) {
	const next = resized(gutter, delta)
	if (next) save(next)
}
function even(gutter) {
	const next = clone(baseTree.value)
	const node = splitAt(resolve(next, shown), gutter.path)
	if (!node?.src) return
	evenAt(node, gutter.index)
	save(next)
}

// --- Moving a tile by its title bar (as in PanelLayout.vue)
const moving = shallowRef(null)
const preview = computed(() => {
	const drop = moving.value?.drop
	if (!drop) return null
	if (!drop.target) {
		const share = PAGE_EDGE_SHARE
		return {
			left: { x: 0, y: 0, w: room.w * share, h: room.h },
			right: { x: room.w * (1 - share), y: 0, w: room.w * share, h: room.h },
			top: { x: 0, y: 0, w: room.w, h: room.h * share },
			bottom: { x: 0, y: room.h * (1 - share), w: room.w, h: room.h * share },
		}[drop.side]
	}
	const t = geometry.value.tiles.find((tile) => tile.id === drop.target)
	if (!t) return null
	return {
		center: t,
		left: { ...t, w: t.w / 2 },
		right: { ...t, x: t.x + t.w / 2, w: t.w / 2 },
		top: { ...t, h: t.h / 2 },
		bottom: { ...t, y: t.y + t.h / 2, h: t.h / 2 },
	}[drop.side]
})
function pointInArea(event) {
	const rect = area.value.getBoundingClientRect()
	return { x: event.clientX - rect.left, y: event.clientY - rect.top }
}
function startMove(id, event) {
	if (event.button !== 0) return
	moving.value = { id, start: { x: event.clientX, y: event.clientY }, active: false, drop: null }
	event.currentTarget.setPointerCapture(event.pointerId)
}
function onMove(event) {
	const m = moving.value
	if (!m) return
	if (!buttonDown(event)) return cancelMove()
	if (!m.active && Math.hypot(event.clientX - m.start.x, event.clientY - m.start.y) < 5) return
	if (!m.active) {
		passThrough(true)
		window.addEventListener("keydown", onMoveKey)
	}
	const p = pointInArea(event)
	let drop = dropAt(p.x, p.y, geometry.value.tiles, room)
	if (drop?.target === m.id) drop = null
	moving.value = { ...m, active: true, drop }
}
function endMove() {
	const m = moving.value
	cancelMove()
	if (m?.active && m.drop) save(dropped(baseTree.value, m.id, m.drop))
}
function cancelMove() {
	if (moving.value?.active) {
		passThrough(false)
		window.removeEventListener("keydown", onMoveKey)
	}
	moving.value = null
}
function onMoveKey(event) {
	if (event.key === "Escape") cancelMove()
}
function moveOptions(id) {
	const to = (drop) => () => save(dropped(baseTree.value, id, drop))
	const others = geometry.value.tiles.filter((t) => t.id !== id)
	return [
		{
			group: __("Whole page"),
			items: [
				{ label: __("Full width at the top"), icon: "arrow-up", onClick: to({ target: null, side: "top" }) },
				{ label: __("Full width at the bottom"), icon: "arrow-down", onClick: to({ target: null, side: "bottom" }) },
				{ label: __("Full height on the left"), icon: "arrow-left", onClick: to({ target: null, side: "left" }) },
				{ label: __("Full height on the right"), icon: "arrow-right", onClick: to({ target: null, side: "right" }) },
			],
		},
		...others.map((t) => {
			const name = titleOf(t.id)
			return {
				group: name,
				items: [
					{ label: __("Left of {0}", [name]), onClick: to({ target: t.id, side: "left" }) },
					{ label: __("Right of {0}", [name]), onClick: to({ target: t.id, side: "right" }) },
					{ label: __("Above {0}", [name]), onClick: to({ target: t.id, side: "top" }) },
					{ label: __("Below {0}", [name]), onClick: to({ target: t.id, side: "bottom" }) },
					{ label: __("Swap with {0}", [name]), onClick: to({ target: t.id, side: "center" }) },
				],
			}
		}),
		{ group: __("Layout"), items: [{ label: __("Standard arrangement"), icon: "layout", onClick: reset }] },
	]
}

defineExpose({ makeBig, reset, biggest })
</script>

<style scoped>
/* Each tile glows in the space's colour (PM: keep the glow). */
.meeting-tile {
	border: 3px solid hsl(var(--area-h) 75% 50%);
	background: hsl(var(--area-h) 75% 50% / 0.1);
	box-shadow: 0 0 16px 3px hsl(var(--area-h) 75% 50% / 0.35);
}
.meeting-tile > header {
	background: hsl(var(--area-h) 75% 50% / 0.18);
	border-radius: 0.6rem 0.6rem 0 0;
}
.meeting-tile__button {
	display: flex;
	align-items: center;
	justify-content: center;
	width: 1.25rem;
	height: 1.25rem;
	border-radius: 0.25rem;
	color: var(--ink-gray-6);
}
.meeting-tile__button:hover {
	background: var(--surface-gray-2);
	color: var(--ink-gray-9);
}
</style>

<style>
/* While a splitter or a tile is dragged, frames (the call) must not take the pointer. */
.meeting-tiles--dragging iframe {
	pointer-events: none !important;
}
</style>
