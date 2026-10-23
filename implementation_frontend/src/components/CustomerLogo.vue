<template>
	<img
		v-if="customer?.image"
		:src="customer.image"
		:alt="customer.customer_name"
		class="h-8 w-8 flex-shrink-0 rounded-md border border-outline-gray-1 bg-surface-white object-contain"
	/>
	<span
		v-else
		class="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-surface-gray-7 text-xs font-semibold text-ink-white"
		aria-hidden="true"
	>
		{{ initials }}
	</span>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({ customer: { type: Object, default: null } })

const initials = computed(() => {
	const words = (props.customer?.customer_name || "").split(/\s+/).filter((w) => /^[\p{L}\d]/u.test(w))
	return (words.slice(0, 2).map((w) => w[0]).join("") || "·").toUpperCase()
})
</script>
