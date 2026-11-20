<template>
	<!-- One reported Issue beside the list (#1671): what was reported, where, and where its GitLab
	     issues stand. Scrolls on its own; Esc or ✕ closes it. -->
	<aside class="flex min-h-0 flex-col rounded-lg border border-outline-gray-2 bg-surface-white" :aria-label="__('Issue')">
		<div class="flex items-start gap-2 border-b border-outline-gray-1 px-4 py-2.5">
			<div class="min-w-0 flex-1">
				<div class="text-xs text-ink-gray-5">{{ name }}<template v-if="issue"> · {{ __(issue.status) }}</template></div>
				<h2 class="mt-0.5 text-base font-semibold leading-snug text-ink-gray-9">{{ issue?.subject || "…" }}</h2>
			</div>
			<button type="button" class="rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-9" :aria-label="__('Close')" :title="__('Close (Esc)')" @click="$emit('close')">
				<FeatherIcon name="x" class="h-4 w-4" />
			</button>
		</div>

		<div v-if="error" class="m-4 rounded-lg bg-surface-red-1 p-3 text-sm text-ink-red-4">{{ error }}</div>
		<div v-else-if="!issue" class="p-4 text-sm text-ink-gray-5">{{ __("Loading…") }}</div>
		<div v-else class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3 text-sm">
			<StageLine :stage="issue.stage" :stages="issue.stages" />
			<dl class="grid grid-cols-2 gap-x-4 gap-y-1.5">
				<div class="min-w-0">
					<dt class="text-xs text-ink-gray-5">{{ __("Reported by") }}</dt>
					<dd class="truncate text-ink-gray-8">{{ issue.phriend_reported_by_name || "—" }} · {{ date(issue.opening_date) }}</dd>
				</div>
				<div class="min-w-0">
					<dt class="text-xs text-ink-gray-5">{{ __("Reported on") }}</dt>
					<dd class="truncate text-ink-gray-8" :title="where">{{ where || "—" }}</dd>
				</div>
			</dl>
			<p v-if="issue.phriend_comment" class="whitespace-pre-line text-ink-gray-8">{{ issue.phriend_comment }}</p>

			<section>
				<h3 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("In GitLab") }}</h3>
				<p v-if="!issue.gitlab_issues.length" class="mt-1 text-ink-gray-5">{{ __("No GitLab issue yet. The team looks at the report first.") }}</p>
				<a
					v-for="g in issue.gitlab_issues"
					:key="g.name"
					:href="g.url"
					target="_blank"
					rel="noopener noreferrer"
					class="flex flex-wrap items-center gap-x-2 py-1 hover:text-ink-gray-9"
					:title="__('Open in GitLab')"
				>
					<span class="text-xs font-semibold text-ink-gray-6">{{ g.reference }}</span>
					<span class="min-w-0 flex-1 truncate text-ink-gray-9">{{ g.title }}</span>
					<span class="inline-flex h-5 items-center rounded-full px-1.5 text-xs font-semibold" :class="g.state === 'closed' ? 'bg-surface-green-2 text-ink-green-3' : 'bg-surface-gray-2 text-ink-gray-7'">{{ __(g.state || "open") }}</span>
					<FeatherIcon name="external-link" class="h-3 w-3 text-ink-gray-5" />
					<span v-if="g.labels?.length" class="w-full truncate pl-1 text-xs text-ink-gray-5">{{ g.labels.join(" · ") }}</span>
				</a>
			</section>

			<section v-if="issue.phriend_screenshot">
				<h3 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("Screenshot") }}</h3>
				<a :href="issue.phriend_screenshot" target="_blank" rel="noopener noreferrer">
					<img :src="issue.phriend_screenshot" :alt="__('Screenshot of the report')" class="mt-1 max-h-64 rounded border border-outline-gray-2" />
				</a>
			</section>
		</div>
	</aside>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import dayjs from "dayjs"
import { call, FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import StageLine from "./StageLine.vue"
import spaConfig from "../config"

const props = defineProps({
	implementation: { type: String, required: true },
	name: { type: String, required: true },
})
defineEmits(["close"])

const issue = ref(null)
const error = ref("")

watch(
	() => [props.implementation, props.name],
	async () => {
		issue.value = null
		error.value = ""
		try {
			issue.value = await call(`${spaConfig.api}.get_issue`, { implementation: props.implementation, name: props.name })
		} catch (e) {
			error.value = e?.messages?.[0] || e?.message || __("Could not load the issue")
		}
	},
	{ immediate: true }
)

const where = computed(() => {
	const i = issue.value
	if (!i) return ""
	if (i.phriend_ref_doctype) return `${__(i.phriend_ref_doctype)} ${i.phriend_ref_docname}`
	return readableRoute(i.phriend_route)
})

// Routes are stored as the browser had them ("…/DEMO%20Alpenfrisch/…"); show them readable.
function readableRoute(value) {
	try {
		return decodeURIComponent(value || "")
	} catch (e) {
		return value || ""
	}
}

function date(value) {
	return value ? dayjs(value).format("D MMM YYYY") : ""
}
</script>
