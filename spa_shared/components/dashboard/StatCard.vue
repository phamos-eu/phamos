<template>
	<div class="rounded-lg border border-outline-gray-2 bg-surface-white p-4">
		<div class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ label }}</div>
		<div class="mt-2 text-2xl font-semibold tabular-nums text-ink-gray-9">{{ value }}</div>
		<div v-if="hint" class="mt-1 text-xs text-ink-gray-6">{{ hint }}</div>
		<div v-if="lines.length" class="mt-3 space-y-1 text-xs text-ink-gray-6">
			<div v-for="line in lines" :key="line">{{ line }}</div>
		</div>
		<slot />
	</div>
</template>

<script setup>
defineProps({
	label: { type: String, required: true },
	value: { type: [String, Number], default: "—" },
	hint: { type: String, default: "" },
	lines: { type: Array, default: () => [] },
})
</script>
