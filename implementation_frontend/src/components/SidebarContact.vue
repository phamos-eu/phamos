<template>
	<!-- The customer's contact at phamos. Absence and the acting manager follow in #1676. -->
	<div class="mt-auto flex-shrink-0 border-t border-outline-gray-2 p-2">
		<div v-if="manager" class="flex items-center gap-2" :class="collapsed ? 'justify-center' : 'px-1'">
			<img v-if="manager.image" :src="manager.image" alt="" class="h-7 w-7 flex-shrink-0 rounded-full object-cover" />
			<span
				v-else
				class="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-surface-gray-7 text-2xs font-semibold text-ink-white"
				:title="collapsed ? manager.full_name : undefined"
			>
				{{ initials }}
			</span>
			<template v-if="!collapsed">
				<div class="min-w-0 flex-1">
					<div class="truncate text-xs font-semibold text-ink-gray-9">{{ manager.full_name }}</div>
					<div class="truncate text-2xs text-ink-gray-5">{{ __("Your contact at phamos") }}</div>
				</div>
				<a
					v-if="manager.phone"
					:href="`tel:${manager.phone.replace(/[^\d+]/g, '')}`"
					class="rounded p-1.5 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
					:title="__('Call {0}', [manager.phone])"
					:aria-label="__('Call {0}', [manager.full_name])"
				>
					<FeatherIcon name="phone" class="h-3.5 w-3.5" />
				</a>
				<a
					:href="`mailto:${manager.email}`"
					class="rounded p-1.5 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
					:title="manager.email"
					:aria-label="__('Email {0}', [manager.full_name])"
				>
					<FeatherIcon name="mail" class="h-3.5 w-3.5" />
				</a>
			</template>
		</div>
		<div v-else-if="!collapsed" class="px-1 text-2xs text-ink-gray-5">{{ __("No contact assigned yet") }}</div>
		<!-- Customers have no Desk; internal users keep the way back like in the other cockpits. -->
		<button
			v-if="scope.isInternal"
			type="button"
			class="mt-1 flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm font-medium text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
			:class="collapsed ? 'justify-center' : ''"
			:title="collapsed ? __('Desk') : undefined"
			@click="openDesk()"
		>
			<FeatherIcon name="external-link" class="h-4 w-4 flex-shrink-0" />
			<span v-if="!collapsed" class="truncate">{{ __("Desk") }}</span>
		</button>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { openDesk } from "@spa/utils/appWindow.js"
import { __ } from "@spa/utils/i18n.js"
import { current } from "../implementationStore.js"
import { scope } from "../scopeStore.js"

defineProps({ collapsed: { type: Boolean, default: false } })

const manager = computed(() => current.data?.manager || null)
const initials = computed(() =>
	(manager.value?.full_name || "")
		.split(/\s+/)
		.slice(0, 2)
		.map((w) => w[0] || "")
		.join("")
		.toUpperCase()
)
</script>
