<template>
	<!-- A record page as tiles (#1915): every panel of the record in a tree of splits that always
	     fills the page (tiling.js). Every line between two tiles drags; closed panels live in the
	     rail on the right, the only place to open them again. -->
	<div class="flex h-full min-h-0 min-w-0 flex-1">
		<div ref="area" class="relative min-h-0 min-w-0 flex-1 overflow-hidden bg-surface-gray-2">
			<template v-if="room.w">
				<section
					v-for="tile in geometry.tiles"
					:key="tile.id"
					class="absolute flex flex-col overflow-hidden bg-surface-white"
					:style="box(tile)"
					role="region"
					:aria-label="titleOf(tile.id)"
				>
					<!-- The title bar is the handle to move the panel (#1916): drag it onto another tile or
					     an edge of the page; "Move to…" does the same without a mouse. -->
					<header
						class="flex h-7 flex-none cursor-grab touch-none select-none items-center gap-1.5 border-b border-outline-gray-1 pl-2.5 pr-1"
						:title="__('Drag to move')"
						@pointerdown="(e) => startMove(tile.id, e)"
						@pointermove="onMove"
						@pointerup="endMove"
						@pointercancel="cancelMove"
						@lostpointercapture="cancelMove"
					>
						<FeatherIcon
							v-if="typeof defOf(tile.id)?.icon === 'string'"
							:name="defOf(tile.id).icon"
							class="h-3.5 w-3.5 flex-shrink-0 text-ink-gray-5"
						/>
						<component :is="defOf(tile.id)?.icon" v-else size="sm" class="flex-shrink-0" />
						<span class="flex-shrink-0 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
							{{ titleOf(tile.id) }}
						</span>
						<span v-if="summaryOf(tile.id)" class="min-w-0 truncate text-xs text-ink-gray-5">
							· {{ summaryOf(tile.id) }}
						</span>
						<!-- The panel's own actions, teleported in by its content (hosts.panelTitleSlots) -->
						<TitleSlot :panel-id="tile.id" class="ml-auto" @pointerdown.stop />
						<div class="flex flex-shrink-0 items-center" @pointerdown.stop>
							<Dropdown :options="moveOptions(tile.id)" placement="right">
								<button
									type="button"
									class="flex h-5 w-5 items-center justify-center rounded text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
									:title="__('Move to…')"
									:aria-label="__('Move to…')"
								>
									<FeatherIcon name="move" class="h-3.5 w-3.5" />
								</button>
							</Dropdown>
						</div>
						<button
							type="button"
							class="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
							:title="__('Close {0}', [titleOf(tile.id)])"
							:aria-label="__('Close {0}', [titleOf(tile.id)])"
							@pointerdown.stop
							@click="toggle(tile.id)"
						>
							<FeatherIcon name="x" class="h-3.5 w-3.5" />
						</button>
					</header>
					<!-- The panel's body is teleported in here (see the bodies below). -->
					<div
						:id="tileId(tile.id)"
						class="min-h-0 flex-1"
						:class="defOf(tile.id)?.bare ? 'flex flex-col overflow-hidden' : 'overflow-y-auto p-2'"
					/>
				</section>

				<div
					v-for="(gutter, i) in geometry.gutters"
					:key="`g${i}-${gutter.path.join('.')}-${gutter.index}`"
					role="separator"
					tabindex="0"
					:aria-orientation="gutter.axis === 'w' ? 'vertical' : 'horizontal'"
					:aria-label="__('Resize the panels')"
					:title="__('Drag to resize, double-click to even out')"
					class="group absolute z-[2] flex touch-none items-center justify-center focus:outline-none"
					:class="gutter.axis === 'w' ? 'cursor-col-resize' : 'cursor-row-resize'"
					:style="box(grabArea(gutter))"
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
					<!-- the visible line; the element around it is wider, so it is easy to grab -->
					<span
						class="pointer-events-none rounded-full"
						:class="[
							gutter.axis === 'w' ? 'h-full w-1' : 'h-1 w-full',
							gutterKey(gutter) === draggingKey
								? 'bg-outline-gray-4'
								: 'bg-outline-gray-2 group-hover:bg-outline-gray-3 group-focus-visible:bg-outline-gray-4',
						]"
					/>
				</div>

				<!-- Where a dragged panel will land -->
				<div
					v-if="moving?.active && preview"
					class="pointer-events-none absolute z-[3] rounded-sm border-2 border-blue-500 bg-blue-500/20 transition-all duration-75"
					:style="box(preview)"
				/>

				<div
					v-if="!geometry.tiles.length"
					class="absolute inset-0 flex items-center justify-center bg-surface-white p-6 text-center text-sm text-ink-gray-5"
				>
					{{ __("Open a panel from the bar on the right.") }}
				</div>
			</template>
		</div>

		<PanelRail :items="railItems" @toggle="toggle" @reset="reset" />

		<!-- Closed and squeezed-out panels wait here, mounted, so their badges stay current. -->
		<div :id="parkId" class="hidden" aria-hidden="true" />
		<Teleport v-for="def in defs" :key="def.id" defer :to="`#${visible.has(def.id) && room.w ? tileId(def.id) : parkId}`">
			<PanelBody
				:def="def"
				:doctype="doctype"
				:record="record"
				:open="visible.has(def.id)"
				@state="(state) => (reported[def.id] = state)"
			/>
		</Teleport>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from "vue"
import { Dropdown, FeatherIcon } from "frappe-ui"
import spaConfig from "@/config"
import { __ } from "@spa/utils/i18n.js"
import { issueChatStore } from "@spa/issueChatStore.js"
import { setRavenFramePassThrough } from "@spa/utils/ravenFrame.js"
import PanelBody from "./PanelBody.vue"
import PanelRail from "./PanelRail.vue"
import { DEFAULT_LAYOUTS, PANELS } from "./definitions.js"
import { minimums, panelsFor, places } from "./registry.js"
import {
	PAGE_EDGE_SHARE,
	clone,
	dropAt,
	dropped,
	evenAt,
	fit,
	layout as computeLayout,
	resizeAt,
	resolve,
	sanitize,
	splitAt,
	openingOrder,
	touched,
	withAll,
} from "./tiling.js"
import { usePanelLayout } from "./usePanelLayout.js"
import TitleSlot from "./TitleSlot.vue"

const props = defineProps({
	doctype: { type: String, required: true },
	record: { type: Object, required: true },
})

// Element ids for the tiles and the parking place, unique per page (two layouts never collide).
const uid = `pl-${Math.random().toString(36).slice(2, 9)}`
const parkId = `${uid}-park`
const tileId = (id) => `${uid}-tile-${id}`

const stored = usePanelLayout(props.doctype)
const defaults = DEFAULT_LAYOUTS[props.doctype] || { tree: () => null, opened: [] }

// The panels of this record, and what their bodies reported (badge, summary, hidden).
const defs = computed(() => panelsFor(PANELS, { doctype: props.doctype, record: props.record, cockpitPanels: spaConfig.panels }))
const reported = reactive({})
const defOf = (id) => defs.value.find((d) => d.id === id)
const titleOf = (id) => __(defOf(id)?.title || id)
function summaryOf(id) {
	const def = defOf(id)
	if (def?.summary) {
		try {
			return def.summary(props.record) || ""
		} catch (e) {
			return ""
		}
	}
	return reported[id]?.summary || ""
}

// The room the tiles have, followed as the window or the page around them changes.
const area = ref(null)
const room = reactive({ w: 0, h: 0 })
let observer = null
onMounted(() => {
	// Measure once now: a ResizeObserver reports only when the page renders, which a tab opened in
	// the background doesn't do, and the tiles would wait for it.
	const rect = area.value.getBoundingClientRect()
	room.w = Math.floor(rect.width)
	room.h = Math.floor(rect.height)
	observer = new ResizeObserver(([entry]) => {
		room.w = Math.floor(entry.contentRect.width)
		room.h = Math.floor(entry.contentRect.height)
	})
	observer.observe(area.value)
})
onBeforeUnmount(() => observer?.disconnect())

const mins = computed(() => minimums(defs.value))
const available = computed(() => defs.value.filter((d) => !reported[d.id]?.hidden).map((d) => d.id))
const layoutState = computed(() => stored.get())
const closed = computed(() => new Set(layoutState.value.closed || []))
const opened = computed(() => openingOrder(layoutState.value.opened, defaults.opened))

// The user's tree, else the default for this width; panels it doesn't know yet get placed.
const baseTree = computed(() => {
	const tree = sanitize(layoutState.value.tree) || defaults.tree(room.w || 1200)
	return withAll(tree, available.value, places(defs.value))
})
// A splitter being dragged shows its tree live; it is saved once on release.
const dragTree = shallowRef(null)
const tree = computed(() => dragTree.value || baseTree.value)

const shown = computed(() => new Set(available.value.filter((id) => !closed.value.has(id))))
// Too small a window: panels opened longest ago step back to the rail until there is room.
const squeezed = computed(() => (room.w ? fit(baseTree.value, shown.value, opened.value, mins.value, room) : new Set()))
const visible = computed(() => new Set([...shown.value].filter((id) => !squeezed.value.has(id))))
const resolved = computed(() => resolve(tree.value, visible.value))
const geometry = computed(() =>
	room.w && resolved.value
		? computeLayout(resolved.value, { x: 0, y: 0, w: room.w, h: room.h }, mins.value)
		: { tiles: [], gutters: [] }
)

// A splitter is 4px; its grab area reaches 4px into the tiles on both sides.
const GRAB = 4
const grabArea = (g) =>
	g.axis === "w" ? { ...g, x: g.x - GRAB, w: g.w + 2 * GRAB } : { ...g, y: g.y - GRAB, h: g.h + 2 * GRAB }

const box = (r) => ({ left: `${r.x}px`, top: `${r.y}px`, width: `${r.w}px`, height: `${r.h}px` })

const railItems = computed(() =>
	defs.value
		.filter((d) => !reported[d.id]?.hidden)
		.map((d) => ({
			id: d.id,
			title: titleOf(d.id),
			icon: d.icon,
			open: visible.value.has(d.id),
			squeezed: squeezed.value.has(d.id),
			badge: reported[d.id]?.badge || "",
			tone: reported[d.id]?.tone || "",
			summary: summaryOf(d.id),
		}))
)

function save(patch) {
	stored.set({
		tree: clone(baseTree.value),
		closed: [...closed.value],
		opened: [...opened.value],
		...patch,
	})
}

function toggle(id) {
	if (visible.value.has(id)) {
		save({ closed: [...closed.value, id] })
	} else {
		// closed, or squeezed out: it opens and counts as opened last, so it stays
		save({ closed: [...closed.value].filter((x) => x !== id), opened: touched(opened.value, id) })
	}
}

function reset() {
	stored.reset()
}

// The chat button and the list's chat icon ask for a panel to open (#1911).
watch(
	() => issueChatStore.expandRequest,
	(request) => {
		if (!request || request.record !== props.record?.name) return
		issueChatStore.expandRequest = null
		if (!visible.value.has(request.panel)) toggle(request.panel)
	}
)

// Splitters
const dragging = shallowRef(null)
let dragStart = null
// The gutters are new objects after every re-layout; the one being dragged is found by its place.
const gutterKey = (g) => `${g.path.join(".")}:${g.index}`
const draggingKey = computed(() => (dragging.value ? gutterKey(dragging.value) : null))

function at(axis, event) {
	return axis === "w" ? event.clientX : event.clientY
}

/** A copy of the stored tree with the splitter moved by `delta`, or null. */
function resized(gutter, delta, base = baseTree.value) {
	const next = clone(base)
	const node = splitAt(resolve(next, visible.value), gutter.path)
	if (!node?.src) return null
	resizeAt(node, gutter.index, delta, gutter.avail, mins.value)
	return next
}

function startDrag(gutter, event) {
	dragging.value = gutter
	dragStart = { pos: at(gutter.axis, event), base: clone(baseTree.value) }
	event.currentTarget.setPointerCapture(event.pointerId)
	// the pointer may cross the chat while dragging; Raven's frame must not take it
	setRavenFramePassThrough(true)
}

// Only while the button is down: if the release got lost (the pointer left the window, the
// capture was dropped), a later plain mouse move must not keep resizing.
const buttonDown = (event) => (event.buttons & 1) === 1

function onDrag(event) {
	if (!dragStart) return
	if (!buttonDown(event)) return endDrag()
	dragTree.value = resized(dragging.value, at(dragging.value.axis, event) - dragStart.pos, dragStart.base)
}

function endDrag() {
	if (!dragStart) return
	setRavenFramePassThrough(false)
	if (dragTree.value) save({ tree: dragTree.value })
	dragTree.value = null
	dragging.value = null
	dragStart = null
}

function nudge(gutter, delta) {
	const next = resized(gutter, delta)
	if (next) save({ tree: next })
}

function even(gutter) {
	const next = clone(baseTree.value)
	const node = splitAt(resolve(next, visible.value), gutter.path)
	if (!node?.src) return
	evenAt(node, gutter.index)
	save({ tree: next })
}

// Moving a panel (#1916): drag its title bar; the drop zone under the pointer shows where it lands.
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
	// a few pixels first, so a click on the title bar doesn't start a move
	if (!m.active && Math.hypot(event.clientX - m.start.x, event.clientY - m.start.y) < 5) return
	if (!m.active) {
		setRavenFramePassThrough(true)
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
	if (m?.active && m.drop) applyDrop(m.id, m.drop)
}

function cancelMove() {
	if (moving.value?.active) {
		setRavenFramePassThrough(false)
		window.removeEventListener("keydown", onMoveKey)
	}
	moving.value = null
}

function onMoveKey(event) {
	if (event.key === "Escape") cancelMove()
}

function applyDrop(id, drop) {
	save({ tree: dropped(baseTree.value, id, drop), opened: touched(opened.value, id) })
}

// The same moves from the title bar's menu, for the keyboard.
function moveOptions(id) {
	const to = (drop) => () => applyDrop(id, drop)
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
	]
}

// Leaving the page mid-drag: the Raven frame must take clicks again, the Escape listener goes.
onBeforeUnmount(() => {
	if (dragStart || moving.value?.active) setRavenFramePassThrough(false)
	window.removeEventListener("keydown", onMoveKey)
})
</script>
