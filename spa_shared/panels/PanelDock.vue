<template>
	<!-- The dock beside a record (#1910): the record's panels stacked, each a row that expands in
	     place. Resizable at its left edge; order, open panels and width are kept per user. -->
	<aside
		v-if="panels.length"
		v-show="!allHidden"
		class="relative flex min-h-0 min-w-0 flex-none flex-col border-r border-outline-gray-2 bg-surface-white"
		:class="stacked ? 'w-[var(--dock-w)] lg:max-h-[45%] lg:w-auto lg:border-t' : 'w-[var(--dock-w)]'"
		:style="{ '--dock-w': `${width}px` }"
		:aria-label="__('Panels')"
	>
		<div
			role="separator"
			aria-orientation="vertical"
			tabindex="0"
			:aria-label="__('Resize the panels')"
			:aria-valuenow="width"
			:aria-valuemin="MIN_DOCK_WIDTH"
			:aria-valuemax="MAX_DOCK_WIDTH"
			:title="__('Drag to resize, double-click to reset')"
			class="absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize touch-none hover:bg-outline-gray-3 focus:outline-none focus-visible:bg-outline-gray-4"
			:class="[{ 'lg:hidden': stacked }, dragging ? 'bg-outline-gray-4' : '']"
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

		<div class="min-h-0 flex-1 overflow-y-auto">
			<DockedPanel
				v-for="(item, index) in panels"
				:key="item.def.id"
				:panel="item.def"
				:record="record"
				:body-props="bodyProps(item.def)"
				:expanded="item.expanded"
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
import { computed, reactive, ref } from "vue"
import { Button, Dropdown } from "frappe-ui"
import spaConfig from "@/config"
import { __ } from "@spa/utils/i18n.js"
import DockedPanel from "./DockedPanel.vue"
import { PANELS } from "./definitions.js"
import { usePanelLayout } from "./usePanelLayout.js"
import { MAX_DOCK_WIDTH, MIN_DOCK_WIDTH, clamp, dockWidth, moved, panelsFor, toggled } from "./registry.js"

const props = defineProps({
	doctype: { type: String, required: true },
	record: { type: Object, default: null },
	// Below the record instead of beside it (from lg on), e.g. while the Issue chat column is
	// open (IssuesInbox): no resizing then, the height is capped instead.
	stacked: { type: Boolean, default: false },
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
const width = computed(() => dockWidth(panels.value, dragWidth.value ?? layout.get().width))
let dragStart = null

function startDrag(event) {
	dragging.value = true
	dragStart = { x: event.clientX, width: width.value }
	event.currentTarget.setPointerCapture(event.pointerId)
}

function drag(event) {
	if (!dragStart) return
	// the dock sits right of the record: dragging its left edge leftwards widens it
	dragWidth.value = clamp(dragStart.width + dragStart.x - event.clientX, MIN_DOCK_WIDTH, MAX_DOCK_WIDTH)
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

const menu = computed(() => [
	{
		label: __("Reset panel layout"),
		icon: "rotate-ccw",
		onClick: () => layout.reset(),
	},
])
</script>
