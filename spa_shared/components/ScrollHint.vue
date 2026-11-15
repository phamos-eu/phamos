<template>
	<!-- A scroll box that says when it continues (#1922): a fade at a clipped edge and a "More below"
	     pill, the same as the description's (RichTextField scroll-hint). -->
	<div class="relative flex min-h-0 flex-col">
		<div ref="box" class="min-h-0 flex-1 overflow-y-auto" :class="boxClass">
			<slot />
		</div>
		<div
			v-show="overflow.above"
			class="pointer-events-none absolute inset-x-0 top-0 h-6 bg-gradient-to-b from-black/10 to-transparent dark:from-black/40"
			aria-hidden="true"
		/>
		<div
			v-show="overflow.below"
			class="pointer-events-none absolute inset-x-0 bottom-0 flex h-12 items-end justify-center bg-gradient-to-t to-transparent pb-1.5"
			:class="fade"
		>
			<button
				type="button"
				class="pointer-events-auto inline-flex items-center gap-1 rounded-full border border-outline-gray-2 bg-surface-white px-2.5 py-0.5 text-xs font-medium text-ink-gray-7 shadow-sm hover:text-ink-gray-9 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
				:title="__('Scroll to see the rest')"
				@mousedown.prevent
				@click="scrollMore"
			>
				<FeatherIcon name="chevron-down" class="h-3.5 w-3.5" />
				{{ __("More below") }}
			</button>
		</div>
	</div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import { scrollOverflow } from "@spa/utils/scrollOverflow.js"

defineProps({
	/** classes of the scroll box itself (padding, gaps) */
	boxClass: { type: [String, Array, Object], default: "" },
	/** the colour the bottom fade starts from: the background behind the content */
	fade: { type: String, default: "from-white dark:from-gray-900" },
})

const box = ref(null)
const overflow = ref({ above: false, below: false })
let resizeObserver = null
let mutationObserver = null
let frame = 0

function measure() {
	frame = 0
	if (!box.value) return
	// only a real change re-renders: this runs on every scroll and observer tick
	const next = scrollOverflow(box.value)
	if (next.above !== overflow.value.above || next.below !== overflow.value.below) overflow.value = next
}

// Content that loads or grows later (checklists, a teleported panel body) changes the height
// without resizing the box; measure once per frame at most.
function measureSoon() {
	if (!frame) frame = requestAnimationFrame(measure)
}

const observed = new WeakSet()
function observeChildren() {
	// the children, and theirs: a tile's teleport target holds the panel body one level down
	for (const child of box.value?.children || []) {
		for (const el of [child, ...child.children]) {
			if (observed.has(el)) continue
			observed.add(el)
			resizeObserver.observe(el)
		}
	}
}

function scrollMore() {
	box.value?.scrollBy({ top: Math.round(box.value.clientHeight * 0.8), behavior: "smooth" })
}

onMounted(() => {
	box.value.addEventListener("scroll", measureSoon, { passive: true })
	// The box's size, and its content's: content can grow without a DOM change (an image that
	// finishes loading, an editor growing). New children are observed as they come.
	resizeObserver = new ResizeObserver(measureSoon)
	resizeObserver.observe(box.value)
	observeChildren()
	mutationObserver = new MutationObserver(() => {
		observeChildren()
		measureSoon()
	})
	mutationObserver.observe(box.value, { childList: true, subtree: true, characterData: true })
	measure()
})

onBeforeUnmount(() => {
	cancelAnimationFrame(frame)
	box.value?.removeEventListener("scroll", measureSoon)
	resizeObserver?.disconnect()
	mutationObserver?.disconnect()
})
</script>
