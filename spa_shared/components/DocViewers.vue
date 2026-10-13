<template>
	<div v-if="viewers.length" class="flex flex-shrink-0 items-center" :title="title">
		<span
			v-for="(viewer, i) in shown"
			:key="viewer.name"
			class="rounded-full ring-2 ring-white dark:ring-gray-900"
			:class="i ? '-ml-1.5' : ''"
		>
			<UserAvatar size="sm" :name="viewer.name" :label="viewer.full_name" :image="viewer.user_image" />
		</span>
		<span v-if="hidden" class="ml-1 text-xs text-ink-gray-5">+{{ hidden }}</span>
	</div>
</template>

<script setup>
/** Avatars of the other users who have the same document open. */
import { computed } from "vue"
import UserAvatar from "@spa/components/UserAvatar.vue"

const MAX_SHOWN = 4

const props = defineProps({
	viewers: { type: Array, default: () => [] },
})

const shown = computed(() => props.viewers.slice(0, MAX_SHOWN))
const hidden = computed(() => Math.max(0, props.viewers.length - MAX_SHOWN))
const title = computed(
	() => `Also viewing: ${props.viewers.map((v) => v.full_name || v.name).join(", ")}`
)
</script>
