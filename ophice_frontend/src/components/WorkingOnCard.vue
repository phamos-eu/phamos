<template>
	<!-- What someone works on right now (#2064): the Implementation; the issue only as a detail. -->
	<div
		class="flex min-w-0 items-start gap-1.5 rounded-md border border-outline-gray-2 bg-surface-gray-1 px-2 py-1 text-xs"
		data-testid="working-on"
	>
		<FeatherIcon name="briefcase" class="mt-0.5 h-3 w-3 flex-shrink-0 text-ink-gray-5" />
		<span class="min-w-0 flex-1">
			<a
				v-if="card.url"
				:href="card.url"
				target="_blank"
				rel="noopener"
				class="block truncate font-medium text-ink-gray-8 hover:underline"
				:title="__('Open the Implementation')"
				@click.stop
			>{{ card.customer_name || card.implementation }}</a>
			<span v-else class="block truncate font-medium text-ink-gray-8">{{ card.project_name }}</span>
			<span v-if="card.url && card.project_name" class="block truncate text-ink-gray-5">{{ card.project_name }}</span>
			<a
				v-if="card.issue"
				:href="card.issue.url"
				target="_blank"
				rel="noopener"
				class="flex items-center gap-1 truncate text-ink-gray-5 hover:text-ink-gray-8 hover:underline"
				:title="card.issue.title"
				@click.stop
			>
				<FeatherIcon name="gitlab" class="h-3 w-3 flex-shrink-0" />
				<span class="truncate">{{ card.issue.title }}</span>
			</a>
		</span>
	</div>
</template>

<script setup>
import { FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

defineProps({
	/** { implementation, customer_name, project_name, url, issue: { title, url } | null } */
	card: { type: Object, required: true },
})
</script>
