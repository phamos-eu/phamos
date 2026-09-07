<template>
	<div ref="root" class="relative flex-shrink-0">
		<button
			type="button"
			class="flex h-7 w-7 items-center justify-center rounded border border-gray-300 bg-white text-gray-600 hover:bg-gray-100 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
			:class="{
				'border-gray-900 text-gray-900 dark:border-gray-300 dark:text-gray-100': modelValue,
			}"
			:aria-label="ariaLabel"
			@click.stop="toggle"
		>
			<FeatherIcon name="filter" class="h-3.5 w-3.5" />
		</button>
		<div
			v-if="open"
			class="absolute right-0 top-full z-20 mt-1 w-44 rounded-md border border-gray-200 bg-white py-1 shadow-lg dark:border-gray-700 dark:bg-gray-800"
		>
			<button
				type="button"
				class="block w-full px-3 py-1.5 text-left text-xs hover:bg-gray-50 dark:hover:bg-gray-700"
				:class="
					!modelValue
						? 'font-medium text-gray-900 dark:text-gray-100'
						: 'text-gray-600 dark:text-gray-400'
				"
				@click="setValue(false)"
			>
				{{ activeLabel }}
			</button>
			<button
				type="button"
				class="block w-full px-3 py-1.5 text-left text-xs hover:bg-gray-50 dark:hover:bg-gray-700"
				:class="
					modelValue
						? 'font-medium text-gray-900 dark:text-gray-100'
						: 'text-gray-600 dark:text-gray-400'
				"
				@click="setValue(true)"
			>
				{{ includeLabel }}
			</button>
		</div>
	</div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue"

defineProps({
	modelValue: { type: Boolean, default: false },
	activeLabel: { type: String, required: true },
	includeLabel: { type: String, required: true },
	ariaLabel: { type: String, default: "Filter" },
})

const emit = defineEmits(["update:modelValue"])

const open = ref(false)
const root = ref(null)

function toggle() {
	open.value = !open.value
}

function setValue(value) {
	open.value = false
	emit("update:modelValue", value)
}

function onDocClick(event) {
	if (!open.value) return
	if (root.value && !root.value.contains(event.target)) {
		open.value = false
	}
}

onMounted(() => {
	document.addEventListener("click", onDocClick)
})

onBeforeUnmount(() => {
	document.removeEventListener("click", onDocClick)
})
</script>
