<template>
	<span :class="tone" class="whitespace-nowrap rounded px-1.5 py-0.5 text-xs">{{ __(status) }}</span>
</template>

<script setup>
import { computed } from "vue"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({ status: { type: String, required: true } })

// Theme tokens only, so the badge reads in light and dark mode alike.
const tone = computed(
	() =>
		({
			Live: "bg-surface-green-2 text-ink-green-4",
			"In Testing": "bg-surface-blue-2 text-ink-blue-3",
			"In Progress": "bg-surface-blue-1 text-ink-blue-3",
			Dropped: "bg-surface-gray-2 text-ink-gray-5 line-through",
		})[props.status] || "bg-surface-gray-2 text-ink-gray-7"
)
</script>
