<template>
	<!--
		A Chip Space chip (#2053): the user's avatar with Phriend's dangling legs
		(same leg shapes as phamos/public/js/phriend/ball.js, viewBox 64×76, ball r=24).
		The root is exactly the avatar (40px), the legs hang outside it, so layout ignores them.
	-->
	<span class="chip-figure relative inline-flex" :class="{ 'is-moving': moving }">
		<svg class="chip-figure__legs" viewBox="0 0 64 76" aria-hidden="true">
			<g class="chip-figure__leg chip-figure__leg--l">
				<path d="M24 48 L20 66" stroke-width="4" stroke-linecap="round" />
				<ellipse cx="17.5" cy="67" rx="5.5" ry="2.6" />
			</g>
			<g class="chip-figure__leg chip-figure__leg--r">
				<path d="M40 48 L44 66" stroke-width="4" stroke-linecap="round" />
				<ellipse cx="46.5" cy="67" rx="5.5" ry="2.6" />
			</g>
		</svg>
		<span class="relative inline-flex rounded-full" :class="{ 'chip-figure__ring': ring }">
			<UserAvatar :name="user" :label="label" :image="image" size="lg" />
		</span>
	</span>
</template>

<script setup>
import UserAvatar from "@spa/components/UserAvatar.vue"

defineProps({
	user: { type: String, default: "" },
	label: { type: String, default: "" },
	image: { type: String, default: "" },
	/** My own chip gets a ring. */
	ring: { type: Boolean, default: false },
	/** Legs kick while the chip moves, and dangle slowly otherwise. */
	moving: { type: Boolean, default: false },
})
</script>

<style scoped>
/* The ball (r=24 in the 64×76 viewBox) is the 40px avatar: 1 unit = 40/48 px. */
.chip-figure__legs {
	position: absolute;
	left: calc(-8px * 40 / 48);
	top: calc(-8px * 40 / 48);
	width: calc(64px * 40 / 48);
	height: calc(76px * 40 / 48);
	overflow: visible;
	pointer-events: none;
}
/* Phriend's legs are black; on a dark page they turn light so they stay visible. */
.chip-figure__leg path {
	stroke: var(--ink-gray-8);
}
.chip-figure__leg ellipse {
	fill: var(--ink-gray-8);
}
.chip-figure__leg {
	transform-box: fill-box;
	transform-origin: 50% 0%;
	animation: chip-dangle-l 2.18s ease-in-out infinite alternate;
}
.chip-figure__leg--r {
	animation-name: chip-dangle-r;
	animation-delay: -1.09s;
}
.is-moving .chip-figure__leg--l {
	animation: chip-wiggle-l 0.18s ease-in-out infinite alternate;
}
.is-moving .chip-figure__leg--r {
	animation: chip-wiggle-r 0.18s ease-in-out infinite alternate;
}
.chip-figure__ring {
	box-shadow: 0 0 0 3px var(--surface-white), 0 0 0 5px var(--ink-blue-3, #3b82f6);
}
/* Same swing as Phriend's wiggle (ball.js), and a slow, small dangle at rest. */
@keyframes chip-wiggle-l {
	from { transform: rotate(-12deg); }
	to { transform: rotate(10deg); }
}
@keyframes chip-wiggle-r {
	from { transform: rotate(12deg); }
	to { transform: rotate(-10deg); }
}
@keyframes chip-dangle-l {
	from { transform: rotate(-5deg); }
	to { transform: rotate(4deg); }
}
@keyframes chip-dangle-r {
	from { transform: rotate(5deg); }
	to { transform: rotate(-4deg); }
}
@media (prefers-reduced-motion: reduce) {
	.chip-figure__leg,
	.is-moving .chip-figure__leg--l,
	.is-moving .chip-figure__leg--r {
		animation: none;
	}
}
</style>
