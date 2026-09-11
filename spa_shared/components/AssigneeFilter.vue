<template>
	<div
		class="flex flex-nowrap items-center justify-start gap-1"
		role="group"
		aria-label="Filter by assignee"
	>
		<button
			v-for="user in users"
			:key="user.name"
			type="button"
			class="shrink-0 rounded-full transition"
			:class="
				isSelected(user.name)
					? 'origin-center scale-[1.15] z-[1] ring-2 ring-outline-gray-4 ring-offset-1 ring-offset-surface-white'
					: 'opacity-70 hover:opacity-100'
			"
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
	/** Currently selected user ids (empty = all) */
	modelValue: { type: Array, default: () => [] },
	/** Available assignees: [{ name, full_name, user_image }] */
	users: { type: Array, default: () => [] },
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
