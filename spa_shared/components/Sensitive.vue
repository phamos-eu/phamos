<template>
	<!--
		A value that privacy mode blurs (#1839). While hidden it can't be selected, copied or hovered,
		so tooltips inside don't give it away either. Outside a cockpit with privacy mode it is a
		plain wrapper.
	-->
	<component
		:is="tag"
		:class="hidden ? 'pointer-events-none select-none blur-[8px]' : ''"
		:aria-hidden="hidden ? 'true' : undefined"
		:title="hidden ? __('Hidden for screen sharing') : undefined"
	>
		<slot />
	</component>
</template>

<script setup>
import { usePrivacyMode } from "@spa/composables/usePrivacyMode.js"
import { __ } from "@spa/utils/i18n.js"

defineProps({
	/** Wrapper element: "span" for inline values, "div" for blocks. */
	tag: { type: String, default: "span" },
})

const { hidden } = usePrivacyMode()
</script>
