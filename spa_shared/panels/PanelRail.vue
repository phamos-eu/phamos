<template>
	<!-- The one place to open a closed panel (#1915): an icon per panel of the record, with its
	     numbers as a badge. Click opens or closes the panel. -->
	<nav
		class="flex w-10 flex-none flex-col items-center gap-1 border-l border-outline-gray-2 bg-surface-gray-1 py-2"
		:aria-label="__('Panels')"
	>
		<button
			v-for="item in items"
			:key="item.id"
			type="button"
			class="relative flex h-8 w-8 items-center justify-center rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
			:class="
				item.open
					? 'bg-surface-white text-ink-gray-9 shadow-sm'
					: 'text-ink-gray-5 hover:bg-surface-gray-3 hover:text-ink-gray-8'
			"
			:aria-pressed="item.open"
			:aria-label="label(item)"
			:title="label(item)"
			@click="$emit('toggle', item.id)"
		>
			<FeatherIcon v-if="typeof item.icon === 'string'" :name="item.icon" class="h-4 w-4" />
			<component :is="item.icon" v-else size="sm" />
			<span
				v-if="item.badge"
				class="absolute -right-1 -top-1 inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full px-1 text-[10px] font-semibold leading-none"
				:class="badgeClass(item)"
				aria-hidden="true"
			>
				{{ item.badge }}
			</span>
		</button>

		<div class="mt-auto">
			<Dropdown :options="menu" placement="right">
				<Button variant="ghost" size="sm" icon="settings" :label="__('Panel settings')" :title="__('Panel settings')" />
			</Dropdown>
		</div>
	</nav>
</template>

<script setup>
import { computed } from "vue"
import { Button, Dropdown, FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

defineProps({
	/** [{ id, title (translated), icon, open, squeezed, badge, tone, summary }] */
	items: { type: Array, required: true },
})
const emit = defineEmits(["toggle", "reset"])

function label(item) {
	const action = item.open ? __("Close {0}", [item.title]) : __("Open {0}", [item.title])
	const parts = [action]
	if (item.summary) parts.push(item.summary)
	if (item.squeezed) parts.push(__("No room in the window"))
	return parts.join(" · ")
}

function badgeClass(item) {
	if (item.tone === "mention") return "bg-surface-red-5 text-ink-white"
	if (item.tone === "new") return "bg-surface-blue-3 text-ink-white"
	return "bg-surface-gray-4 text-ink-gray-8"
}

const menu = computed(() => [{ label: __("Reset panel layout"), icon: "rotate-ccw", onClick: () => emit("reset") }])
</script>
