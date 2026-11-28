<template>
	<!-- One tile of the Team Cockpit's Overview (#2236): a title linking to the full page, and a short
	     summary that never scrolls; what does not fit is cut, the page behind the link has it all. -->
	<section class="flex min-h-0 flex-col overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-white p-4">
		<header class="mb-2 flex flex-shrink-0 items-center gap-2">
			<router-link :to="to" class="min-w-0 flex-1 truncate text-sm font-semibold text-ink-gray-9 hover:underline">
				{{ title }}
			</router-link>
			<slot name="actions" />
			<router-link :to="to" class="flex-shrink-0 text-ink-gray-5 hover:text-ink-gray-8" :aria-label="__('Open {0}', [title])">
				<FeatherIcon name="arrow-right" class="h-4 w-4" />
			</router-link>
		</header>
		<div class="flex min-h-0 flex-1 flex-col overflow-hidden">
			<p v-if="loading" class="text-sm text-ink-gray-5">{{ __("Loading…") }}</p>
			<p v-else-if="missing" class="text-sm text-ink-gray-5">{{ __("Not available") }}</p>
			<slot v-else />
		</div>
	</section>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

defineProps({
	title: { type: String, required: true },
	// the page with the full list
	to: { type: Object, required: true },
	loading: { type: Boolean, default: false },
	// the tile's data could not be loaded (no rights, no GitLab sync, an error)
	missing: { type: Boolean, default: false },
})
</script>
