<template>
	<!-- Our own icons (#2207) where Feather has none; any other name is a Feather icon. -->
	<svg
		v-if="isCustomIcon(name)"
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 0 24 24"
		fill="none"
		stroke="currentColor"
		stroke-width="2"
		stroke-linecap="round"
		stroke-linejoin="round"
		aria-hidden="true"
	>
		<path v-for="(d, i) in CUSTOM_ICON_PATHS[name]" :key="i" :d="d" />
	</svg>
	<FeatherIcon v-else :name="name" />
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"
import { CUSTOM_ICON_PATHS, isCustomIcon } from "../utils/icons.js"

defineProps({
	/** A name from CUSTOM_ICON_PATHS or a Feather icon name */
	name: { type: String, required: true },
})
</script>
