<template>
	<!--
		The mini map's spot in the sidebar (#2155), only inside Ophice: an empty box at the bottom of
		the sidebar that Ophice lays its mini map over, at the sidebar's width. Ophice sets the height
		(the map's own, a drop target while it is dragged, nothing while it hovers).
	-->
	<div v-if="active" class="flex-shrink-0" :class="height ? 'px-2 pb-2' : ''" data-testid="ophice-dock">
		<div
			ref="spot"
			class="flex items-center justify-center rounded-xl text-center text-xs"
			:class="target ? 'border-2 border-dashed border-outline-gray-4 bg-surface-gray-2 px-2 text-ink-gray-6' : ''"
			:style="{ height: `${height}px` }"
		>
			<span v-if="target">{{ __("Drop here to dock the map") }}</span>
		</div>
	</div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue"
import { __ } from "@spa/utils/i18n.js"
import { DOCK_MAX_SHARE, DOCK_RECT, DOCK_SIZE, dockMessage, inOphiceFrame, rectInParent } from "@spa/utils/ophiceDock.js"

const active = inOphiceFrame()
const spot = ref(null)
const height = ref(0)
const target = ref(false)

function post(rect, max = 0) {
	try {
		window.parent.postMessage({ type: DOCK_RECT, rect, max, height: height.value, target: target.value }, window.location.origin)
	} catch {
		// Ophice is gone
	}
}

function report() {
	const el = spot.value
	if (!el) return
	const sidebar = el.closest("aside") || document.documentElement
	post(
		rectInParent(window.frameElement.getBoundingClientRect(), el.getBoundingClientRect()),
		Math.floor(sidebar.clientHeight * DOCK_MAX_SHARE)
	)
}

function onMessage(event) {
	if (event.source !== window.parent) return
	const data = dockMessage(event, DOCK_SIZE)
	if (!data) return
	height.value = Math.max(0, Math.round(Number(data.height) || 0))
	target.value = Boolean(data.target)
	nextTick(report)
}

// The page goes (another cockpit loads in the frame): Ophice must not dock to a spot that's gone.
const gone = () => post(null)
let observer = null
onMounted(() => {
	if (!active) return
	window.addEventListener("message", onMessage)
	window.addEventListener("resize", report)
	window.addEventListener("pagehide", gone)
	observer = new ResizeObserver(report)
	if (spot.value) observer.observe(spot.value)
	// The sidebar's height decides the largest spot.
	const sidebar = spot.value?.closest("aside")
	if (sidebar) observer.observe(sidebar)
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
