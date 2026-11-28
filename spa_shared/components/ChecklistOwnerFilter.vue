<template>
	<div
		class="flex max-w-full items-center overflow-x-auto [justify-content:safe_center]"
		:class="overlap ? '-space-x-1 py-0.5' : 'gap-1'"
		role="group"
		:aria-label="label"
	>
		<button
			v-for="user in users"
			:key="user.name"
			type="button"
			class="relative shrink-0 rounded-full transition-opacity hover:z-10 focus-visible:z-10"
			:class="isSelected(user.name) ? 'opacity-100 ring-2 ring-outline-gray-4' : 'opacity-45 hover:opacity-80'"
			:aria-pressed="isSelected(user.name)"
			:title="user.full_name || user.name"
			@click="toggle(user.name)"
		>
			<UserAvatar
				:name="user.name"
				:label="user.full_name || user.name"
				:image="user.user_image"
				size="sm"
			/>
		</button>
	</div>
</template>

<script setup>
import { computed } from "vue"
import UserAvatar from "@spa/components/UserAvatar.vue"

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	users: { type: Array, default: () => [] },
	/** Accessible name of the group; the Issue list filters by assignee with it. */
	label: { type: String, default: "Filter by owner" },
	/** Overlap the avatars a little, so a few more fit a narrow column. */
	overlap: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue"])
const selected = computed(() => new Set(props.modelValue || []))

function isSelected(name) {
	return selected.value.has(name)
}

function toggle(name) {
	const next = new Set(selected.value)
	if (next.has(name)) next.delete(name)
	else next.add(name)
	emit("update:modelValue", [...next])
}
</script>
