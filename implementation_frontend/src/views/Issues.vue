<template>
	<!-- Issues reported through Phriend about this implementation (#1671). Opened from Phriend it shows
	     the reports of the place it was opened from; the switcher widens it on purpose. -->
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-5xl flex-col gap-4">
			<div>
				<h1 class="text-lg font-semibold text-ink-gray-9">{{ heading }}</h1>
				<p class="mt-0.5 text-sm text-ink-gray-6">{{ __("Each report shows how far it is: reported, in GitLab, in progress, testing, done.") }}</p>
			</div>
			<div class="flex flex-wrap items-center gap-3">
				<TabButtons v-model="scope" :buttons="scopeButtons" />
				<label class="flex items-center gap-2 text-sm text-ink-gray-7">
					<input v-model="includeClosed" type="checkbox" class="rounded border-outline-gray-3" />
					{{ __("Include done") }}
				</label>
			</div>

			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">{{ error }}</div>

			<section class="overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-white">
				<router-link
					v-for="issue in issues"
					:key="issue.name"
					:to="{ name: 'IssueDetail', params: { implementation, name: issue.name }, query: route.query }"
					class="flex flex-col gap-1.5 border-b border-outline-gray-1 px-4 py-3 hover:bg-surface-gray-1"
				>
					<div class="flex items-center gap-3">
						<span class="text-xs font-semibold text-ink-gray-6">{{ issue.name }}</span>
						<span class="min-w-0 flex-1 truncate text-sm font-medium text-ink-gray-9">{{ issue.subject }}</span>
						<StageLine :stage="issue.stage" :stages="stages" compact />
					</div>
					<div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-gray-6">
						<span>{{ issue.phriend_reported_by_name || "—" }} · {{ date(issue.opening_date) }}</span>
						<span v-if="issue.phriend_ref_doctype">{{ __(issue.phriend_ref_doctype) }} {{ issue.phriend_ref_docname }}</span>
						<span v-else-if="issue.phriend_route" class="truncate">{{ readableRoute(issue.phriend_route) }}</span>
						<a
							v-for="g in issue.gitlab_issues"
							:key="g.name"
							:href="g.url"
							target="_blank"
							rel="noopener noreferrer"
							class="inline-flex items-center gap-1 text-ink-gray-7 underline underline-offset-2 hover:text-ink-gray-9"
							@click.stop
						>
							{{ g.reference }}
							<FeatherIcon name="external-link" class="h-3 w-3" />
						</a>
					</div>
				</router-link>
				<div v-if="!loading && !issues.length" class="px-4 py-8 text-center text-sm text-ink-gray-5">{{ emptyText }}</div>
				<div v-if="loading" class="px-4 py-8 text-center text-sm text-ink-gray-5">{{ __("Loading…") }}</div>
			</section>
		</div>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import dayjs from "dayjs"
import { call, TabButtons } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import StageLine from "../components/StageLine.vue"
import spaConfig from "../config"

const props = defineProps({ implementation: { type: String, required: true } })

const route = useRoute()
const router = useRouter()

const SCOPE_LABELS = { record: "This record", page: "This page", mine: "Reported by me", implementation: "Whole implementation" }

const issues = ref([])
const available = ref([])
const counts = ref({})
const stages = ref(["Reported", "In GitLab", "In Progress", "Testing", "Done"])
const loading = ref(false)
const error = ref("")
const includeClosed = ref(false)

// The scope is part of the URL, so a link from Phriend opens the narrow view and Back keeps it.
const scope = computed({
	get: () => route.query.scope || "",
	set: (value) => router.replace({ query: { ...route.query, scope: value } }),
})
const scopeButtons = computed(() =>
	available.value.map((s) => ({ label: `${__(SCOPE_LABELS[s])} (${counts.value[s] ?? 0})`, value: s }))
)
// What the list shows, in words: the place Phriend was opened on, or the wider scope picked.
const heading = computed(() => {
	const current = route.query.scope
	if (current === "record" && route.query.ref_docname)
		return __("Reports about {0} {1}", [__(route.query.ref_doctype), route.query.ref_docname])
	if (current === "page" && route.query.route) return __("Reports made on {0}", [readableRoute(route.query.route)])
	if (current === "mine") return __("Reports you made")
	return __("All reports of this implementation")
})
const emptyText = computed(() =>
	includeClosed.value ? __("No issues reported here.") : __("No open issues reported here.")
)

// The scope the server picked; writing it into the URL must not load the list a second time.
let echoedScope = null
let requestId = 0

watch(() => [props.implementation, route.query.scope, route.query.route, route.query.ref_docname, includeClosed.value], () => {
	if (echoedScope && route.query.scope === echoedScope) {
		echoedScope = null
		return
	}
	load()
}, {
	immediate: true,
})

async function load() {
	const id = ++requestId
	loading.value = true
	error.value = ""
	try {
		const data = await call(`${spaConfig.api}.get_issues`, {
			implementation: props.implementation,
			scope: route.query.scope || null,
			route: route.query.route || null,
			ref_doctype: route.query.ref_doctype || null,
			ref_docname: route.query.ref_docname || null,
			include_closed: includeClosed.value ? 1 : 0,
		})
		if (id !== requestId) return // a newer request (other scope or implementation) wins
		issues.value = data?.issues || []
		available.value = data?.available || []
		counts.value = data?.counts || {}
		stages.value = data?.stages || stages.value
		if (data?.scope && data.scope !== route.query.scope) {
			echoedScope = data.scope
			router.replace({ query: { ...route.query, scope: data.scope } })
		}
	} catch (e) {
		if (id === requestId) error.value = e?.messages?.[0] || e?.message || __("Could not load the issues")
	} finally {
		if (id === requestId) loading.value = false
	}
}

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
