<template>
	<!-- Phriend's ball as a small mark: the record came from Phriend (#1901). Static SVG, no user data.
	     In dark mode it glows like the ball, so it shows on a black page (#1934). -->
	<span
		class="inline-block flex-shrink-0 align-[-2px] [&_svg]:h-full [&_svg]:w-full dark:[filter:drop-shadow(0_0_1.5px_rgba(255,255,255,0.6))_drop-shadow(0_0_3px_rgba(255,255,255,0.3))]"
		:class="sizeClass"
		role="img"
		:aria-label="label"
		:title="label"
		v-html="logo"
	/>
</template>

<script setup>
import { computed } from "vue"
import { SVG } from "@phriend/ball.js"
import { __ } from "@spa/utils/i18n.js"
import { typeLabel } from "@spa/utils/phriendReport.js"

const props = defineProps({
	type: { type: String, default: "" },
	size: { type: String, default: "sm" },
})

// each mark gets its own gradient id; the ball and other marks are on the same page
const logo = SVG.replace(/phriend-grad/g, `phriend-grad-${Math.random().toString(36).slice(2, 9)}`)
const sizeClass = computed(() => (props.size === "md" ? "h-5 w-5" : "h-3.5 w-3.5"))
const label = computed(() =>
	props.type ? __("Phriend report: {0}", [typeLabel(props.type)]) : __("Phriend report"),
)
</script>
