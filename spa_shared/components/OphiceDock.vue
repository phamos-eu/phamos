<template>
	<!--
		The mini map's right sidebar (#2155), only inside Ophice. Docked, it is a column at the right
		of the cockpit, which Ophice lays its mini map over. While the map is dragged, a drop strip
		shows over the right edge instead, so the page does not jump. Hovering: nothing here.
	-->
	<aside
		v-if="active && (docked || target)"
		class="flex w-72 flex-col p-2"
		:class="
			docked
				? 'h-full flex-none border-l border-outline-gray-2 bg-surface-white dark:bg-surface-gray-1'
				: 'fixed inset-y-0 right-0 z-[100] bg-surface-gray-1/80 backdrop-blur-sm'
		"
		data-testid="ophice-dock"
	>
		<div
			ref="spot"
			class="flex min-h-0 flex-1 items-center justify-center rounded-xl text-center text-xs"
			:class="target ? 'border-2 border-dashed border-outline-gray-4 px-4 text-ink-gray-6' : ''"
		>
			<span v-if="target">{{ __("Drop here to dock the map") }}</span>
		</div>
	</aside>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { __ } from "@spa/utils/i18n.js"
import { DOCK_RECT, DOCK_SIZE, dockMessage, inOphiceFrame, rectInParent } from "@spa/utils/ophiceDock.js"

const active = inOphiceFrame()
const spot = ref(null)
const docked = ref(false)
const target = ref(false)

/** Tell Ophice: is there a dock (`available`), and where is its spot (null while it is closed). */
function post(available = true) {
	const el = available ? spot.value : null
	const rect = el ? rectInParent(window.frameElement.getBoundingClientRect(), el.getBoundingClientRect()) : null
	try {
		window.parent.postMessage(
			{ type: DOCK_RECT, available, rect, docked: docked.value, target: target.value },
			window.location.origin
		)
	} catch {
		// Ophice is gone
	}
}
const report = () => post(true)

function onMessage(event) {
	if (event.source !== window.parent) return
	const data = dockMessage(event, DOCK_SIZE)
	if (!data) return
	docked.value = Boolean(data.docked)
	target.value = Boolean(data.target) && !docked.value
	nextTick(report)
}

// The spot's size changes with the window; the spot itself comes and goes.
const observer = active ? new ResizeObserver(report) : null
watch(
	spot,
	(el) => {
		observer?.disconnect()
		if (el) observer?.observe(el)
	},
	{ flush: "post" }
)

// The page goes (another cockpit loads in the frame): Ophice must not dock to a spot that's gone.
const gone = () => post(false)
onMounted(() => {
	if (!active) return
	window.addEventListener("message", onMessage)
	window.addEventListener("resize", report)
	window.addEventListener("pagehide", gone)
	nextTick(report)
})
onBeforeUnmount(() => {
	if (!active) return
	window.removeEventListener("message", onMessage)
	window.removeEventListener("resize", report)
	window.removeEventListener("pagehide", gone)
	observer?.disconnect()
	gone()
})
</script>
