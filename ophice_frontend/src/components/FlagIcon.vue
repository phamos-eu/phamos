<template>
	<!-- A flag pole with a swallowtail cloth (#2130): the colour, and the pattern drawn over it. -->
	<svg viewBox="0 0 24 24" class="ophice-flag-icon" aria-hidden="true" :style="{ '--flag-hue': hue }">
		<defs v-if="pattern !== 'plain'">
			<pattern v-if="pattern === 'dots'" :id="id" width="3" height="3" patternUnits="userSpaceOnUse">
				<circle cx="1.5" cy="1.5" r="0.75" class="ophice-flag-icon__mark" />
			</pattern>
			<pattern v-else-if="pattern === 'stripes'" :id="id" width="3" height="3" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
				<rect width="1.2" height="3" class="ophice-flag-icon__mark" />
			</pattern>
			<pattern v-else-if="pattern === 'grid'" :id="id" width="3" height="3" patternUnits="userSpaceOnUse">
				<path d="M 3 0 L 0 0 0 3" fill="none" stroke-width="0.6" class="ophice-flag-icon__line" />
			</pattern>
			<pattern v-else-if="pattern === 'waves'" :id="id" width="4" height="2.5" patternUnits="userSpaceOnUse">
				<path d="M 0 1.6 Q 1 0.4 2 1.6 T 4 1.6" fill="none" stroke-width="0.6" class="ophice-flag-icon__line" />
			</pattern>
		</defs>
		<ellipse cx="7" cy="21.6" rx="3" ry="1" class="ophice-flag-icon__hole" />
		<line x1="7" y1="2.5" x2="7" y2="21.6" stroke-width="1.4" stroke-linecap="round" class="ophice-flag-icon__pole" />
		<path :d="CLOTH" class="ophice-flag-icon__cloth" />
		<path v-if="pattern !== 'plain'" :d="CLOTH" :fill="`url(#${id})`" />
		<path :d="CLOTH" fill="none" stroke-width="0.6" class="ophice-flag-icon__edge" />
	</svg>
</template>

<script>
let next = 0
</script>

<script setup>
import { computed } from "vue"
import { flagHue } from "../utils/ophiceFlag.js"

const props = defineProps({
	color: { type: String, default: "red" },
	pattern: { type: String, default: "plain" },
})

const CLOTH = "M 7.6 3 H 20.5 L 17.4 7.5 L 20.5 12 H 7.6 Z"
const id = `ophice-flag-pattern-${++next}`
const hue = computed(() => flagHue(props.color))
</script>

<style scoped>
.ophice-flag-icon {
	display: block;
	width: 100%;
	height: 100%;
	overflow: visible;
}
.ophice-flag-icon__cloth {
	fill: hsl(var(--flag-hue) 72% 48%);
}
.ophice-flag-icon__edge {
	stroke: hsl(var(--flag-hue) 72% 30%);
}
.ophice-flag-icon__mark {
	fill: rgb(255 255 255 / 0.7);
}
.ophice-flag-icon__line {
	stroke: rgb(255 255 255 / 0.75);
}
.ophice-flag-icon__pole {
	stroke: #6b4f32;
}
.ophice-flag-icon__hole {
	fill: rgb(60 40 20 / 0.35);
}
</style>
