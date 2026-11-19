<template>
	<div class="flex h-full items-start justify-center overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mt-10 max-w-md rounded-lg border border-outline-gray-2 bg-surface-white p-6 text-center">
			<h2 class="text-base font-semibold text-ink-gray-9">
				{{ scope.error ? __("Could not load your implementations") : __("No implementation shared with you yet") }}
			</h2>
			<p class="mt-1 text-sm text-ink-gray-6">
				{{ scope.error || __("Please contact your project manager at phamos to get access.") }}
			</p>
		</div>
	</div>
</template>

<script setup>
import { __ } from "@spa/utils/i18n.js"
import { scope } from "../scopeStore.js"
</script>
