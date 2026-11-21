<template>
	<!-- The meeting of the area I stand in (#2060). Leaving the area (or Esc, or "Leave") leaves it. -->
	<div
		class="flex w-96 flex-col overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-white text-ink-gray-9 shadow-xl"
		role="region"
		:aria-label="__('Meeting {0}', [area.title])"
		data-testid="meeting-panel"
	>
		<header class="flex items-center gap-2 border-b border-outline-gray-2 px-3 py-2">
			<FeatherIcon name="video" class="h-4 w-4 flex-shrink-0 text-ink-gray-6" />
			<span class="min-w-0 flex-1 truncate text-sm font-medium">{{ area.title }}</span>
			<button
				type="button"
				class="flex-shrink-0 rounded px-1.5 py-0.5 text-xs text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8"
				:title="__('Leave the meeting')"
				@click="$emit('leave')"
			>
				{{ __("Leave (Esc)") }}
			</button>
		</header>
		<VideoCall
			:domain="area.jitsi_domain"
			:room="area.jitsi_room"
			:display-name="displayName"
			@joined="giveKeysBack"
			@stolen="giveKeysBack"
		/>
	</div>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import VideoCall from "./VideoCall.vue"

defineProps({
	/** { title, jitsi_domain, jitsi_room } */
	area: { type: Object, required: true },
	displayName: { type: String, default: "" },
})
defineEmits(["leave"])

// Jitsi may focus its frame by itself: the keys belong to the Space (walking out leaves).
function giveKeysBack() {
	if (document.activeElement?.tagName !== "IFRAME") return
	document.activeElement.blur()
	window.focus()
}
</script>
