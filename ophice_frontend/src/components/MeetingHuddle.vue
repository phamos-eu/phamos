<template>
	<!-- The people in my meeting (#2067), above the area chat: a huddle in the area's colour. -->
	<!-- Someone who leaves floats up out of the huddle and the others close up; newcomers fade in. -->
	<TransitionGroup
		tag="div"
		name="huddle"
		class="relative flex flex-shrink-0 flex-wrap items-start gap-3 rounded-xl px-3 py-2.5"
		@before-leave="keepPlace"
		:style="frameStyle"
		:aria-label="__('In {0}', [area.title])"
		data-testid="meeting-huddle"
	>
		<button
			v-for="person in people"
			:key="person.user"
			type="button"
			class="flex w-14 flex-col items-center gap-1"
			:class="person.user === me ? 'cursor-default' : 'cursor-pointer'"
			:title="person.user === me ? __('{0} (you)', [person.full_name]) : person.full_name"
			data-testid="huddle-person"
			@click="person.user !== me && $emit('pick', person, $event)"
		>
			<span class="block rounded-full" :style="ringStyle(person)">
				<UserAvatar :name="person.user" :label="person.full_name" :image="person.user_image" size="lg" />
			</span>
			<span class="w-full truncate text-center text-[11px] text-ink-gray-8">
				{{ person.user === me ? __("you") : firstName(person) }}
			</span>
		</button>
	</TransitionGroup>
</template>

<script setup>
import { computed } from "vue"
import UserAvatar from "@spa/components/UserAvatar.vue"
import { __ } from "@spa/utils/i18n.js"
import { ringHue } from "../utils/ophiceColor.js"

const props = defineProps({
	/** { name, title, color_hue } */
	area: { type: Object, required: true },
	/** chips in the area: { user, full_name, user_image }, me first */
	people: { type: Array, default: () => [] },
	me: { type: String, default: "" },
})
defineEmits(["pick"])

const frameStyle = computed(() => {
	const h = props.area.color_hue
	// The frame itself is the column around people and chat (#2078); here only a tint.
	return { background: `hsl(${h} 75% 50% / 0.14)` }
})

function ringStyle(person) {
	const ring = person.user === props.me ? "rgb(37,99,235)" : `hsl(${ringHue(person.user)} 80% 45%)`
	return { boxShadow: `0 0 0 2px var(--surface-white, #fff), 0 0 0 4px ${ring}` }
}

/**
 * The one who leaves keeps its place while it fades: taken out of the flow at the spot where it
 * stands, so the others slide into the gap at once (the huddle-move transition, transform only).
 * Measured here because an absolute item in a wrapping flex row would jump to the first slot.
 */
function keepPlace(el) {
	el.style.left = `${el.offsetLeft}px`
	el.style.top = `${el.offsetTop}px`
	el.style.width = `${el.offsetWidth}px`
	el.style.position = "absolute"
}

function firstName(person) {
	return (person.full_name || person.user).split(" ")[0]
}
</script>

<style scoped>
/* Compositor-only: opacity and transform. */
.huddle-enter-active {
	animation: huddle-in 300ms ease-out both;
}
.huddle-leave-active {
	pointer-events: none;
	transition: opacity 400ms ease-out, transform 400ms ease-out;
}
.huddle-leave-to {
	opacity: 0;
	transform: translateY(-10px) scale(0.9);
}
.huddle-move {
	transition: transform 300ms ease;
}
@keyframes huddle-in {
	from { opacity: 0; transform: scale(0.85); }
}
@media (prefers-reduced-motion: reduce) {
	.huddle-enter-active {
		animation-duration: 1ms;
	}
	.huddle-leave-active,
	.huddle-move {
		transition: none;
	}
}
</style>
