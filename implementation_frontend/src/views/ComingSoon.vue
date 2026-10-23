<template>
	<div class="flex h-full items-start justify-center overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mt-10 max-w-md rounded-lg border border-dashed border-outline-gray-2 bg-surface-white p-6 text-center">
			<FeatherIcon name="tool" class="mx-auto h-5 w-5 text-ink-gray-5" />
			<h2 class="mt-3 text-base font-semibold text-ink-gray-9">{{ __("{0} is coming soon", [__(section)]) }}</h2>
			<p class="mt-1 text-sm text-ink-gray-6">{{ __("We are building this part of the cockpit.") }}</p>
			<p v-if="scope.isInternal" class="mt-3 text-xs text-ink-gray-5">phamos/phamos {{ issue }}</p>
		</div>
	</div>
</template>

<script setup>
import { __ } from "@spa/utils/i18n.js"
import { scope } from "../scopeStore.js"

defineProps({
	implementation: { type: String, required: true },
	section: { type: String, required: true },
	issue: { type: String, default: "" },
})
</script>
