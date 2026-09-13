<template>
	<div ref="root" class="relative flex-shrink-0">
		<button
			type="button"
			class="flex h-7 w-7 items-center justify-center rounded border border-outline-gray-2 bg-surface-white text-ink-gray-5 hover:bg-surface-gray-2"
			:class="{
				'border-outline-gray-5 text-ink-gray-9': modelValue,
			}"
			:aria-label="ariaLabel"
			@click.stop="toggle"
		>
			<FeatherIcon name="filter" class="h-3.5 w-3.5" />
		</button>
		<div
			v-if="open"
			class="absolute right-0 top-full z-20 mt-1 w-44 rounded-md border border-outline-gray-2 bg-surface-modal py-1 shadow-lg"
		>
			<button
				type="button"
				class="block w-full px-3 py-1.5 text-left text-xs hover:bg-surface-gray-2"
				:class="!modelValue ? 'font-medium text-ink-gray-9' : 'text-ink-gray-5'"
				@click="setValue(false)"
			>
				{{ activeLabel }}
			</button>
			<button
				type="button"
				class="block w-full px-3 py-1.5 text-left text-xs hover:bg-surface-gray-2"
				:class="modelValue ? 'font-medium text-ink-gray-9' : 'text-ink-gray-5'"
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
