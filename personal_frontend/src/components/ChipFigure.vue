<template>
	<!--
		A Ophice chip (#2053): the user's avatar with Phriend's dangling legs
		(same leg shapes as phamos/public/js/phriend/ball.js, viewBox 64×76, ball r=24).
		The root is exactly the avatar (40px), the legs hang outside it, so layout ignores them.
	-->
	<span
		class="chip-figure relative inline-flex"
		:class="{ 'is-moving': moving, 'is-jumping': jumping, 'is-double': doubleJump, 'is-flying': flying, 'is-offline': offline }"
	>
		<!-- Small angel wings while hovering (Space held after a jump, PM 2026-11-22). Behind the avatar. -->
		<span v-if="flying" class="chip-figure__wings" aria-hidden="true">
			<svg class="chip-figure__wing chip-figure__wing--l" viewBox="0 0 24 18">
				<path d="M23 9 C17 0 6 -1 1 4 C5 5 7 7 4 10 C9 11 11 12 8 16 C14 17 19 14 23 11 Z" />
			</svg>
			<svg class="chip-figure__wing chip-figure__wing--r" viewBox="0 0 24 18">
				<g transform="matrix(-1 0 0 1 24 0)"><path d="M23 9 C17 0 6 -1 1 4 C5 5 7 7 4 10 C9 11 11 12 8 16 C14 17 19 14 23 11 Z" /></g>
			</svg>
		</span>
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
		<span
			class="chip-figure__ring relative inline-flex rounded-full"
			:class="{ 'chip-figure__ring--mine': ring }"
			:style="{ '--ring-h': ringHue }"
		>
			<UserAvatar :name="user" :label="label" :image="image" size="lg" />
		</span>
	</span>
</template>

<script setup>
import { computed } from "vue"
import UserAvatar from "@spa/components/UserAvatar.vue"

const props = defineProps({
	user: { type: String, default: "" },
	label: { type: String, default: "" },
	image: { type: String, default: "" },
	/** My own chip gets a ring. */
	ring: { type: Boolean, default: false },
	/** Legs kick while the chip moves, and dangle slowly otherwise. */
	moving: { type: Boolean, default: false },
	/** In the air (Space): a hop with the legs tucked up. */
	jumping: { type: Boolean, default: false },
	/** The second hop of a double jump. */
	doubleJump: { type: Boolean, default: false },
	/** Hovering with wings (Space held after a jump). */
	flying: { type: Boolean, default: false },
	/** Away and the page closed: greyed out. */
	offline: { type: Boolean, default: false },
})

// Every person gets their own ring colour, the same on every screen (PM: easier to tell apart).
// Blues are left out: blue is my own ring.
const ringHue = computed(() => {
	let hash = 0
	for (const char of props.user) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
	const hue = hash % 300
	return hue >= 190 ? hue + 60 : hue
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
/* The hop (Ophice, Space): up and down once, legs tucked while in the air. */
.chip-figure.is-jumping {
	animation: chip-hop 420ms ease-out;
}
.is-jumping .chip-figure__leg--l,
.is-jumping .chip-figure__leg--r {
	animation: none;
	transform: scaleY(0.6);
}
@keyframes chip-hop {
	0% { transform: translateY(0); }
	45% { transform: translateY(-55%) scale(1.08); }
	100% { transform: translateY(0); }
}
/* A strong ring around every chip (PM 2026-11-22): white, the person's colour, a dark edge,
   so a chip stands out on any map. Mine is blue, wider and glowing. */
.chip-figure__ring {
	box-shadow: 0 0 0 2px #fff, 0 0 0 5px hsl(var(--ring-h, 30) 80% 45%), 0 0 0 6px rgba(0, 0, 0, 0.5);
}
.chip-figure__ring--mine {
	box-shadow: 0 0 0 2px #fff, 0 0 0 6px rgb(37, 99, 235), 0 0 0 7px rgba(0, 0, 0, 0.55),
		0 0 12px 7px rgba(59, 130, 246, 0.6);
}
.is-offline {
	opacity: 0.55;
	filter: grayscale(1);
}
/* Double jump: a second, higher hop (a new animation name restarts it). */
.chip-figure.is-jumping.is-double {
	animation: chip-hop-double 420ms ease-out;
}
@keyframes chip-hop-double {
	0% { transform: translateY(-20%); }
	45% { transform: translateY(-80%) scale(1.12); }
	100% { transform: translateY(0); }
}
/* Hovering: up in the air, bobbing gently, legs tucked, wings flapping. */
.chip-figure.is-flying {
	animation: chip-hover 900ms ease-in-out infinite alternate;
}
.is-flying .chip-figure__leg--l,
.is-flying .chip-figure__leg--r {
	animation: none;
	transform: scaleY(0.6);
}
@keyframes chip-hover {
	from { transform: translateY(-45%); }
	to { transform: translateY(-58%); }
}
.chip-figure__wings {
	position: absolute;
	inset: 0;
	pointer-events: none;
}
.chip-figure__wing {
	position: absolute;
	top: 2px;
	width: 27px;
	height: 20px;
	overflow: visible;
}
.chip-figure__wing path {
	fill: #fff;
	stroke: rgba(15, 23, 42, 0.55);
	stroke-width: 1;
	stroke-linejoin: round;
}
.chip-figure__wing--l {
	left: -22px;
	transform-origin: 100% 55%;
	animation: chip-flap-l 220ms ease-in-out infinite alternate;
}
.chip-figure__wing--r {
	right: -22px;
	transform-origin: 0% 55%;
	animation: chip-flap-r 220ms ease-in-out infinite alternate;
}
@keyframes chip-flap-l {
	from { transform: rotate(18deg); }
	to { transform: rotate(-22deg); }
}
@keyframes chip-flap-r {
	from { transform: rotate(-18deg); }
	to { transform: rotate(22deg); }
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
	.chip-figure.is-jumping,
	.chip-figure.is-flying,
	.chip-figure__wing,
	.chip-figure__leg,
	.is-moving .chip-figure__leg--l,
	.is-moving .chip-figure__leg--r {
		animation: none;
	}
}
</style>
