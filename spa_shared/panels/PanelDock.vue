<template>
	<!-- The dock beside a record (#1910): the record's panels stacked, each a row that expands in
	     place. Resizable at its left edge; order, open panels and width are kept per user.
	     No border of its own: the description and the properties column draw the lines, and the
	     chat needs every pixel of its 768 (Raven's touch layout starts below that, #1613). -->
	<aside
		v-if="panels.length"
		v-show="!allHidden"
		class="relative flex min-h-0 min-w-0 flex-none flex-col bg-surface-white"
		:style="{
			width: `${width}px`,
			// The record keeps at least 20rem, except next to a panel that needs its width (the
			// chat: Raven falls back to its touch layout below 768px).
			maxWidth: needsWidth ? 'none' : 'calc(100% - 20rem)',
		}"
		:aria-label="__('Panels')"
	>
		<!-- No splitter while a panel that needs its width (the chat) is expanded: the dock is then
		     exactly that wide, and the user's width comes back when it is collapsed. -->
		<div
			v-if="!needsWidth"
			role="separator"
			aria-orientation="vertical"
			tabindex="0"
			:aria-label="__('Resize the panels')"
			:aria-valuenow="width"
			:aria-valuemin="MIN_DOCK_WIDTH"
			:aria-valuemax="MAX_DOCK_WIDTH"
			:title="__('Drag to resize, double-click to reset')"
			class="absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize touch-none hover:bg-outline-gray-3 focus:outline-none focus-visible:bg-outline-gray-4"
			:class="dragging ? 'bg-outline-gray-4' : ''"
			@pointerdown="startDrag"
			@pointermove="drag"
			@pointerup="endDrag"
			@pointercancel="endDrag"
			@dblclick="resetWidth"
			@keydown.left.prevent="nudge(16)"
			@keydown.right.prevent="nudge(-16)"
		/>

		<div class="flex items-center justify-end px-2 pt-1">
			<Dropdown :options="menu" placement="right">
				<Button variant="ghost" size="sm" icon="settings" :label="__('Panel settings')" :title="__('Panel settings')" />
			</Dropdown>
		</div>

		<!-- A filling panel (the chat) takes the remaining height and the dock doesn't scroll: the
		     Raven frame is laid over the page (utils/ravenFrame.js) and would not be clipped. -->
		<div class="flex min-h-0 flex-1 flex-col" :class="filling ? 'overflow-hidden' : 'overflow-y-auto'">
			<DockedPanel
				v-for="(item, index) in panels"
				:key="item.def.id"
				:panel="item.def"
				:record="record"
				:body-props="bodyProps(item.def)"
				:expanded="item.expanded"
				:constrained="filling && !item.def.fill"
				:can-move-up="index > 0"
				:can-move-down="index < panels.length - 1"
				@toggle="toggle(item)"
				@move="(step) => move(item, step)"
				@hidden="(value) => (hiddenIds[item.def.id] = value)"
			/>
		</div>
	</aside>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { Button, Dropdown } from "frappe-ui"
import spaConfig from "@/config"
import { __ } from "@spa/utils/i18n.js"
import DockedPanel from "./DockedPanel.vue"
import { PANELS } from "./definitions.js"
import { usePanelLayout } from "./usePanelLayout.js"
import { issueChatStore } from "@spa/issueChatStore.js"
import { MAX_DOCK_WIDTH, MIN_DOCK_WIDTH, clamp, dockWidth, moved, panelsFor, toggled } from "./registry.js"

const props = defineProps({
	doctype: { type: String, required: true },
	record: { type: Object, default: null },
})

const layout = usePanelLayout(props.doctype)

const panels = computed(() =>
	panelsFor(PANELS, {
		doctype: props.doctype,
		record: props.record,
		cockpitPanels: spaConfig.panels,
		layout: layout.get(),
	})
)

// Panels whose body said it has nothing to show (e.g. no permission); the dock goes away
// when that is all of them, instead of leaving an empty column.
const hiddenIds = reactive({})
const allHidden = computed(() => panels.value.every((p) => hiddenIds[p.def.id]))

const shownPanels = computed(() => panels.value.filter((p) => !hiddenIds[p.def.id]))
const shownExpanded = computed(() => panels.value.filter((p) => p.expanded && !hiddenIds[p.def.id]))
const filling = computed(() => shownExpanded.value.some((p) => p.def.fill))
const needsWidth = computed(() => shownExpanded.value.some((p) => p.def.minWidth > 0))

function bodyProps(def) {
	return def.props({ doctype: props.doctype, record: props.record, api: spaConfig.api })
}

function toggle(item) {
	layout.set(toggled(layout.get(), item.def.id, !item.expanded, item.defaultExpanded))
}

function move(item, step) {
	const shown = panels.value.map((p) => p.def.id)
	layout.set(moved(layout.get(), shown, item.def.id, step))
}

// Width: the stored one, overridden live while dragging and saved once on release.
const dragWidth = ref(null)
const dragging = ref(false)
// Hidden panels (e.g. the chat below lg) don't ask for their width.
const width = computed(() => dockWidth(shownPanels.value, dragWidth.value ?? layout.get().width))
let dragStart = null
const REM = typeof document !== "undefined" ? parseFloat(getComputedStyle(document.documentElement).fontSize) || 16 : 16

function startDrag(event) {
	dragging.value = true
	// from the rendered width: the record keeps at least 20rem (max-w above), so a stored
	// width can be wider than what is shown on a small screen
	const shown = event.currentTarget.parentElement.getBoundingClientRect().width
	dragStart = { x: event.clientX, width: shown || width.value }
	event.currentTarget.setPointerCapture(event.pointerId)
}

function drag(event) {
	if (!dragStart) return
	// the dock sits right of the record: dragging its left edge leftwards widens it
	const room = event.currentTarget.parentElement.parentElement.clientWidth - REM * 20
	const max = Math.max(MIN_DOCK_WIDTH, Math.min(MAX_DOCK_WIDTH, room))
	dragWidth.value = clamp(dragStart.width + dragStart.x - event.clientX, MIN_DOCK_WIDTH, max)
}

function endDrag() {
	if (!dragStart) return
	dragStart = null
	dragging.value = false
	if (dragWidth.value != null) saveWidth(dragWidth.value)
	dragWidth.value = null
}

function nudge(step) {
	saveWidth(clamp(width.value + step, MIN_DOCK_WIDTH, MAX_DOCK_WIDTH))
}

function saveWidth(value) {
	layout.set({ ...layout.get(), width: Math.round(value) })
}

function resetWidth() {
	const { width: _drop, ...rest } = layout.get()
	layout.set(rest)
}

// The chat button in the record's top bar asks to expand the collapsed chat panel (#1911).
watch(
	() => issueChatStore.expandRequest,
	(request) => {
		if (!request || request.record !== props.record?.name) return
		issueChatStore.expandRequest = null
		const item = panels.value.find((p) => p.def.id === request.panel)
		if (item && !item.expanded) toggle(item)
	}
)

const menu = computed(() => [
	{
		label: __("Reset panel layout"),
		icon: "rotate-ccw",
		onClick: () => layout.reset(),
	},
])
</script>
