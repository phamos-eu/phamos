<template>
	<!-- Top bar control of privacy mode (#1839): "Show data", then a countdown that extends on click. -->
	<div v-if="enabled" class="flex items-center gap-1">
		<button
			v-if="hidden"
			type="button"
			:class="buttonClass"
			:title="__('Figures are hidden for screen sharing. Show them for {0}.', [duration])"
			@click="reveal"
		>
			<FeatherIcon name="eye" class="h-4 w-4" />
			<span>{{ __("Show data") }}</span>
		</button>
		<template v-else>
			<button
				type="button"
				:class="[buttonClass, 'tabular-nums', secondsLeft <= 10 ? 'text-ink-amber-3' : '']"
				:title="__('Click to extend')"
				:aria-label="__('Data visible for {0}. Click to extend.', [countdown])"
				@click="extend"
			>
				<FeatherIcon name="clock" class="h-4 w-4" />
				<span>{{ countdown }}</span>
			</button>
			<button type="button" :class="buttonClass" :title="__('Hide now')" :aria-label="__('Hide now')" @click="hide">
				<FeatherIcon name="eye-off" class="h-4 w-4" />
			</button>
		</template>
	</div>
</template>

<script setup>
import { computed } from "vue"
import { FeatherIcon } from "frappe-ui"
import { usePrivacyMode } from "@spa/composables/usePrivacyMode.js"
import { __ } from "@spa/utils/i18n.js"

const { enabled, hidden, secondsLeft, revealSeconds, reveal, extend, hide } = usePrivacyMode()

const buttonClass =
	"inline-flex h-7 items-center gap-1.5 rounded-md border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8 hover:bg-surface-gray-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"

function clock(seconds) {
	return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`
}
const countdown = computed(() => clock(secondsLeft.value))
const duration = computed(() => clock(revealSeconds.value))
</script>
