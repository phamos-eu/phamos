<template>
	<!-- What a project management view is and why we use it (#1972): one line, more on request.
	     The cockpit teaches the methods by design; a handbook link can follow later. -->
	<div class="rounded-lg border border-outline-gray-2 bg-surface-white px-4 py-3 text-sm">
		<div class="flex items-start gap-2">
			<FeatherIcon name="info" class="mt-0.5 h-4 w-4 shrink-0 text-ink-gray-5" />
			<p class="flex-1 text-ink-gray-7">{{ summary }}</p>
			<button type="button" class="shrink-0 text-ink-gray-6 underline underline-offset-2 hover:text-ink-gray-9" @click="open = !open">
				{{ open ? __("Less") : __("Learn more") }}
			</button>
		</div>
		<div v-if="open" class="mt-2 flex flex-col gap-2 pl-6 text-ink-gray-7">
			<p v-for="(text, index) in details" :key="index">{{ text }}</p>
		</div>
	</div>
</template>

<script setup>
import { ref } from "vue"
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

defineProps({
	summary: { type: String, required: true },
	details: { type: Array, default: () => [] },
})

const open = ref(false)
</script>
