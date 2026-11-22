<template>
	<!--
		How to keep a call on top (#2078): Chrome's own picture-in-picture on a video, by right-click.
		Ophice cannot start it itself (the call runs on
		Jitsi's page), so it explains it. Chrome and Edge only.
	-->
	<div
		class="w-72 space-y-2 rounded-xl border border-outline-gray-2 bg-surface-white p-3 text-xs text-ink-gray-8 shadow-2xl"
		role="note"
		data-testid="pip-tip"
	>
		<div class="flex items-center gap-2">
			<PopOutIcon class="h-4 w-4 flex-shrink-0 text-ink-gray-6" />
			<span class="flex-1 text-sm font-medium text-ink-gray-9">{{ __("Keep the video on top") }}</span>
			<button type="button" class="rounded p-0.5 text-ink-gray-5 hover:bg-surface-gray-2" :title="__('Close')" @click="$emit('close')">
				<FeatherIcon name="x" class="h-3.5 w-3.5" />
			</button>
		</div>
		<p>{{ __("Right-click a person's video and choose \"Picture in picture\". If a small menu of the call opens first, right-click again.") }}</p>
		<p>
			{{ __("The video then floats above all windows, also when you go back to another tab or app.") }}
		</p>
		<div class="flex justify-end">
			<Button size="sm" variant="subtle" data-testid="pip-tip-ok" @click="$emit('close')">{{ __("Got it") }}</Button>
		</div>
	</div>
</template>

<script setup>
import { Button, FeatherIcon } from "frappe-ui"
import PopOutIcon from "./PopOutIcon.vue"
import { __ } from "@spa/utils/i18n.js"

defineEmits(["close"])

</script>
