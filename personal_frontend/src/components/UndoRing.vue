<template>
	<button
		type="button"
		class="relative flex h-7 items-center gap-1.5 rounded px-1.5 text-sm text-ink-gray-8 hover:bg-surface-gray-2"
		:aria-label="label || __('Undo')"
		:title="label || __('Undo')"
		@click="emit('undo')"
	>
		<svg class="h-6 w-6 -rotate-90" viewBox="0 0 24 24" aria-hidden="true">
			<circle cx="12" cy="12" r="10" fill="none" stroke-width="2.5" style="stroke: var(--surface-gray-3)" />
			<circle
				cx="12"
				cy="12"
				r="10"
				fill="none"
				stroke-width="2.5"
				stroke-linecap="round"
				class="undo-ring"
				:style="{ stroke: 'var(--ink-gray-7)', strokeDasharray: CIRCUMFERENCE, animationDuration: `${seconds}s` }"
			/>
			<text x="12" y="12" class="rotate-90 origin-center fill-current text-[9px]" text-anchor="middle" dominant-baseline="central">
				{{ remaining }}
			</text>
		</svg>
		<span>{{ __("Undo") }}</span>
	</button>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue"

const props = defineProps({
	seconds: { type: Number, default: 10 },
	label: { type: String, default: "" },
})
const emit = defineEmits(["undo", "expired"])

const CIRCUMFERENCE = 2 * Math.PI * 10
const remaining = ref(props.seconds)
let timer = null

onMounted(() => {
	timer = setInterval(() => {
		remaining.value -= 1
		if (remaining.value <= 0) {
			clearInterval(timer)
			emit("expired")
		}
	}, 1000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<style scoped>
.undo-ring {
	stroke-dashoffset: 0;
	animation-name: undo-drain;
	animation-timing-function: linear;
	animation-fill-mode: forwards;
}
@keyframes undo-drain {
	to {
		stroke-dashoffset: 62.832;
	}
}
@media (prefers-reduced-motion: reduce) {
	.undo-ring {
		animation: none;
	}
}
</style>
