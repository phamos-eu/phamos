<template>
	<ul class="space-y-1" :aria-label="__('GitLab issues')">
		<li v-for="row in issues" :key="row.name">
			<a
				:href="row.url"
				target="_blank"
				rel="noopener"
				class="block rounded-md px-2 py-1.5 hover:bg-surface-gray-2"
				:title="__('Open in GitLab')"
			>
				<span class="flex items-baseline gap-2">
					<span class="flex-shrink-0 text-sm font-medium text-ink-gray-9">{{ row.reference }}</span>
					<span class="truncate text-sm text-ink-gray-8">{{ row.title }}</span>
				</span>
				<span class="mt-1 flex flex-wrap items-center gap-1">
					<Badge
						:label="row.state === 'closed' ? __('Closed') : __('Open')"
						:theme="row.state === 'closed' ? 'gray' : 'green'"
						size="sm"
						variant="subtle"
					/>
					<Badge v-for="label in row.labels" :key="label" :label="label" theme="gray" size="sm" variant="outline" />
				</span>
			</a>
		</li>
	</ul>
</template>

<script setup>
// The GitLab issues created from an Issue (GitLab Issue records linked to it), in the Issue
// page's dock. Created from the Desk form ("Create GitLab Issue"); one Issue can hold several.
import { Badge } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

defineProps({
	// get_issue's `gitlab_issues`: see phamos/phriend/gitlab_issues.py issue_gitlab_issues
	issues: { type: Array, required: true },
	embedded: { type: Boolean, default: false },
})
</script>
