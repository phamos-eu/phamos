<template>
	<a
		v-if="document && record"
		:href="deskRecordUrl(document, record)"
		target="_blank"
		rel="noopener noreferrer"
		class="group/ref flex h-9 max-w-full items-center gap-1.5 rounded-md border border-outline-gray-2 bg-surface-white px-2 hover:border-outline-gray-3 hover:bg-surface-gray-2"
		:title="`Open ${document} ${record} in Desk`"
		@click.stop
	>
		<span class="min-w-0 text-left leading-tight">
			<span class="block truncate text-[10px] uppercase tracking-wide text-ink-gray-5">
				{{ document }}
			</span>
			<span class="block truncate text-xs font-medium text-ink-gray-8">{{ record }}</span>
		</span>
		<FeatherIcon
			name="external-link"
			class="h-3 w-3 shrink-0 text-ink-gray-5 group-hover/ref:text-ink-gray-8"
		/>
	</a>
	<span v-else class="text-xs text-ink-gray-5">—</span>
</template>

<script setup>
import { deskRecordUrl } from "@spa/utils/deskUrl.js"

defineProps({
	document: { type: String, default: "" },
	record: { type: String, default: "" },
})
</script>
