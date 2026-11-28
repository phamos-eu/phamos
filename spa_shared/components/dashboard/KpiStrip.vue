<template>
	<!-- Key figures in one compact strip instead of tall tiles, so the table below keeps the room. -->
	<section class="grid gap-px overflow-hidden rounded-lg border border-outline-gray-2 bg-outline-gray-1" :class="gridClass">
		<div v-for="item in items" :key="item.label" class="min-w-0 bg-surface-white px-3 py-2">
			<div class="truncate text-xs text-ink-gray-5" :title="item.label">{{ item.label }}</div>
			<div class="truncate text-lg font-semibold tabular-nums leading-tight text-ink-gray-9">{{ item.value }}</div>
			<div v-if="item.hint" class="truncate text-xs text-ink-gray-5" :title="item.hint">{{ item.hint }}</div>
		</div>
	</section>
</template>

<script setup>
defineProps({
	// [{ label, value, hint? }]
	items: { type: Array, required: true },
	gridClass: { type: String, default: "grid-cols-2 lg:grid-cols-4" },
})
</script>
