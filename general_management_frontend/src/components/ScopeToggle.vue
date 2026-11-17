<template>
	<!-- "Own department / All departments" on the Tasks Gantt (#1948). -->
	<div class="flex flex-shrink-0 items-center rounded border border-outline-gray-2 bg-surface-gray-2 p-0.5" role="group">
		<button
			v-for="option in OPTIONS"
			:key="option.value"
			type="button"
			class="whitespace-nowrap rounded px-2 py-0.5 text-[11px]"
			:class="
				modelValue === option.value
					? 'bg-surface-white font-medium text-ink-gray-9 shadow-sm dark:bg-surface-gray-4'
					: 'text-ink-gray-5 hover:text-ink-gray-8'
			"
			:aria-pressed="modelValue === option.value"
			@click="emit('update:modelValue', option.value)"
		>
			{{ __(option.label) }}
		</button>
	</div>
</template>

<script setup>
import { __ } from "@spa/utils/i18n.js"

defineProps({ modelValue: { type: String, required: true } })
const emit = defineEmits(["update:modelValue"])

const OPTIONS = [
	{ value: "own", label: "Own department" },
	{ value: "all", label: "All departments" },
]
</script>
