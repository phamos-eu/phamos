<template>
	<!-- What a project management view is and why we use it (#1972): one short line; the rest opens
	     as a popover, so it never pushes the content down. A handbook link can follow later. -->
	<div ref="root" class="relative flex min-w-0 items-center gap-1.5 text-xs text-ink-gray-6">
		<FeatherIcon name="info" class="h-3.5 w-3.5 shrink-0" />
		<span class="truncate" :title="summary">{{ summary }}</span>
		<button
			type="button"
			class="shrink-0 underline underline-offset-2 hover:text-ink-gray-9"
			:aria-expanded="open"
			@click="open = !open"
		>
			{{ __("Learn more") }}
		</button>
		<div
			v-if="open"
			class="absolute left-0 top-full z-20 mt-1 flex w-[min(32rem,90vw)] flex-col gap-2 rounded-lg border border-outline-gray-2 bg-surface-white p-3 text-sm text-ink-gray-7 shadow-lg"
			role="dialog"
		>
			<p class="font-medium text-ink-gray-9">{{ summary }}</p>
			<p v-for="(text, index) in details" :key="index">{{ text }}</p>
		</div>
	</div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

defineProps({
	summary: { type: String, required: true },
	details: { type: Array, default: () => [] },
})

const open = ref(false)
const root = ref(null)

// Esc or a click elsewhere closes it, like any popover.
function close(event) {
	if (!open.value) return
	if (event.type === "keydown" ? event.key === "Escape" : !root.value?.contains(event.target)) open.value = false
}
onMounted(() => {
	document.addEventListener("click", close)
	document.addEventListener("keydown", close)
})
onBeforeUnmount(() => {
	document.removeEventListener("click", close)
	document.removeEventListener("keydown", close)
})
</script>
