<template>
	<div class="flex min-w-[7rem] items-center gap-2">
		<div class="h-1.5 min-w-[3rem] flex-1 overflow-hidden rounded-full bg-surface-gray-3" role="progressbar" :aria-valuenow="value" aria-valuemin="0" aria-valuemax="100">
			<div class="h-full rounded-full" :class="value >= 100 ? 'bg-surface-green-3' : 'bg-surface-gray-7'" :style="{ width: `${Math.min(100, value || 0)}%` }" />
		</div>
		<span class="w-9 text-right text-xs tabular-nums text-ink-gray-6">{{ value || 0 }}%</span>
	</div>
</template>

<script setup>
defineProps({ value: { type: Number, default: 0 } })
</script>
