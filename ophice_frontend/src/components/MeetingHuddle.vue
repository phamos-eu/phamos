<template>
	<!-- The people in my meeting (#2067), above the area chat: a huddle in the area's colour. -->
	<div
		class="flex flex-shrink-0 flex-wrap items-start rounded-xl"
		:class="compact ? 'gap-2 px-2 py-1.5' : 'gap-3 px-3 py-2.5'"
		:style="frameStyle"
		:aria-label="__('In {0}', [area.title])"
		data-testid="meeting-huddle"
	>
		<button
			v-for="person in people"
			:key="person.user"
			type="button"
			class="flex flex-col items-center gap-1"
			:class="[compact ? 'w-10' : 'w-14', person.user === me ? 'cursor-default' : 'cursor-pointer']"
			:title="person.user === me ? __('{0} (you)', [person.full_name]) : person.full_name"
			data-testid="huddle-person"
			@click="person.user !== me && $emit('pick', person, $event)"
		>
			<span class="block rounded-full" :style="ringStyle(person)">
				<UserAvatar
					:name="person.user"
					:label="person.full_name"
					:image="person.user_image"
					:size="compact ? 'sm' : 'lg'"
				/>
			</span>
			<span class="w-full truncate text-center text-ink-gray-8" :class="compact ? 'text-[10px]' : 'text-[11px]'">
				{{ person.user === me ? __("you") : firstName(person) }}
			</span>
		</button>
	</div>
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
	/** Smaller chips (encounter call, #2108). */
	compact: { type: Boolean, default: false },
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

function firstName(person) {
	return (person.full_name || person.user).split(" ")[0]
}
</script>
