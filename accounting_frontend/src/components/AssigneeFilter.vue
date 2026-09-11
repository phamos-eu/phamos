<template>
	<div
		class="flex max-w-full flex-nowrap items-center justify-start gap-1 overflow-x-auto"
		role="group"
		aria-label="Filter by assignee"
	>
		<button
			v-for="user in users"
			:key="user.name"
			type="button"
			class="shrink-0 rounded-full transition-opacity"
			:class="isSelected(user.name) ? 'opacity-100' : 'opacity-40 hover:opacity-70'"
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
import UserAvatar from "./UserAvatar.vue"

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
