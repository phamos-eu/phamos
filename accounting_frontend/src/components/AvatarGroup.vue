<template>
	<div
		class="avatar-group group/avatars inline-flex items-center"
		:class="
			align === 'center'
				? 'justify-center'
				: align === 'right'
					? 'justify-end'
					: 'justify-start'
		"
		:title="title"
	>
		<template v-if="visibleUsers.length">
			<span
				v-for="(user, index) in visibleUsers"
				:key="user.name || index"
				class="avatar-group-item relative transition-[margin] duration-100"
				:class="index === 0 ? '' : '-ml-2 group-hover/avatars:-ml-1'"
			>
				<UserAvatar
					:name="user.name"
					:label="user.full_name || user.name"
					:image="user.user_image"
					:size="size"
				/>
			</span>
			<span
				v-if="overflowCount > 0"
				class="avatar-group-item relative -ml-2 transition-[margin] duration-100 group-hover/avatars:-ml-1"
			>
				<span
					class="inline-flex items-center justify-center rounded-full bg-surface-gray-3 font-medium text-ink-gray-7"
					:class="overflowSizeClass"
					:title="overflowTitle"
				>
					+{{ overflowCount }}
				</span>
			</span>
		</template>
		<span v-else-if="showEmpty" class="text-xs text-ink-gray-5">Unassigned</span>
	</div>
</template>

<script setup>
import { computed } from "vue"
import UserAvatar from "./UserAvatar.vue"

const props = defineProps({
	/** [{ name, full_name, user_image }] */
	users: { type: Array, default: () => [] },
	/** Max avatars before +N (Desk list uses 3) */
	limit: { type: Number, default: 3 },
	size: { type: String, default: "sm" },
	align: {
		type: String,
		default: "right",
		validator: (v) => ["left", "right", "center"].includes(v),
	},
	showEmpty: { type: Boolean, default: true },
})

const users = computed(() => props.users || [])

const overflowSizeClass = computed(() => {
	const map = {
		xs: "h-4 w-4 text-[9px]",
		sm: "h-7 w-7 text-xs",
		md: "h-8 w-8 text-sm",
	}
	return map[props.size] || map.sm
})

/** Match frappe.avatar_group: if exactly one over limit, show it; else +N. */
const visibleUsers = computed(() => {
	const list = users.value
	if (list.length <= props.limit + 1) return list
	return list.slice(0, props.limit)
})

const overflowCount = computed(() => {
	const total = users.value.length
	if (total <= props.limit + 1) return 0
	return total - props.limit
})

const overflowTitle = computed(() =>
	users.value
		.slice(props.limit)
		.map((u) => u.full_name || u.name)
		.join(", ")
)

const title = computed(() =>
	users.value.map((u) => u.full_name || u.name).filter(Boolean).join(", ")
)
</script>
