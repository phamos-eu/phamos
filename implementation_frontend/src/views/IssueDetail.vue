<template>
	<!-- One reported Issue (#1671): what was reported, where, and where its GitLab issues stand. -->
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-4xl flex-col gap-4">
			<router-link
				:to="{ name: 'Issues', params: { implementation }, query: route.query }"
				class="inline-flex items-center gap-1 self-start text-sm text-ink-gray-6 hover:text-ink-gray-9"
			>
				<FeatherIcon name="arrow-left" class="h-4 w-4" />
				{{ __("Back to the issues") }}
			</router-link>

			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">{{ error }}</div>
			<div v-else-if="!issue" class="text-sm text-ink-gray-5">{{ __("Loading…") }}</div>
			<template v-else>
				<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<div class="text-xs font-semibold text-ink-gray-6">{{ issue.name }} · {{ __(issue.status) }}</div>
					<h1 class="mt-1 text-lg font-semibold text-ink-gray-9">{{ issue.subject }}</h1>
					<div class="mt-3"><StageLine :stage="issue.stage" :stages="issue.stages" /></div>
					<dl class="mt-4 grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
						<div>
							<dt class="text-xs text-ink-gray-5">{{ __("Reported by") }}</dt>
							<dd class="text-ink-gray-8">{{ issue.phriend_reported_by_name || "—" }} · {{ date(issue.opening_date) }}</dd>
						</div>
						<div>
							<dt class="text-xs text-ink-gray-5">{{ __("Reported on") }}</dt>
							<dd class="truncate text-ink-gray-8">
								<template v-if="issue.phriend_ref_doctype">{{ __(issue.phriend_ref_doctype) }} {{ issue.phriend_ref_docname }}</template>
								<template v-else>{{ issue.phriend_route || "—" }}</template>
							</dd>
						</div>
					</dl>
					<p v-if="issue.phriend_comment" class="mt-4 whitespace-pre-line text-sm text-ink-gray-8">{{ issue.phriend_comment }}</p>
				</section>

				<section class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<h2 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("In GitLab") }}</h2>
					<p v-if="!issue.gitlab_issues.length" class="mt-2 text-sm text-ink-gray-5">{{ __("No GitLab issue yet. The team looks at the report first.") }}</p>
					<ul v-else class="mt-2 flex flex-col">
						<li v-for="g in issue.gitlab_issues" :key="g.name" class="flex flex-wrap items-center gap-3 border-t border-outline-gray-1 py-2.5 first:border-t-0">
							<span class="text-xs font-semibold text-ink-gray-6">{{ g.reference }}</span>
							<span class="min-w-0 flex-1 truncate text-sm text-ink-gray-9">{{ g.title }}</span>
							<span class="inline-flex h-5 items-center rounded-full px-1.5 text-xs font-semibold" :class="g.state === 'closed' ? 'bg-surface-green-2 text-ink-green-3' : 'bg-surface-gray-2 text-ink-gray-7'">{{ __(g.state || "open") }}</span>
							<span v-for="label in g.labels" :key="label" class="text-xs text-ink-gray-6">{{ label }}</span>
							<Button size="sm" @click="openGitLab(g.url)">
								<template #suffix><FeatherIcon name="external-link" class="h-3.5 w-3.5" /></template>
								{{ __("Open in GitLab") }}
							</Button>
						</li>
					</ul>
				</section>

				<section v-if="issue.phriend_screenshot" class="rounded-lg border border-outline-gray-2 bg-surface-white p-5">
					<h2 class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("Screenshot") }}</h2>
					<a :href="issue.phriend_screenshot" target="_blank" rel="noopener noreferrer">
						<img :src="issue.phriend_screenshot" :alt="__('Screenshot of the report')" class="mt-2 max-h-96 rounded border border-outline-gray-2" />
					</a>
				</section>
			</template>
		</div>
	</div>
</template>

<script setup>
import { ref, watch } from "vue"
import { useRoute } from "vue-router"
import dayjs from "dayjs"
import { call } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import StageLine from "../components/StageLine.vue"
import spaConfig from "../config"

const props = defineProps({
	implementation: { type: String, required: true },
	name: { type: String, required: true },
})

const route = useRoute()
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

function openGitLab(url) {
	window.open(url, "_blank", "noopener")
}

function date(value) {
	return value ? dayjs(value).format("D MMM YYYY") : ""
}
</script>
