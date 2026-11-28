<template>
	<!-- Issues reported through Phriend about this implementation (#1671). Opened from Phriend it shows
	     the reports of the place it was opened from; the switcher widens it on purpose. -->
	<!-- Full height: the list scrolls inside its frame, a report opens in the side panel beside it. -->
	<div class="flex h-full min-h-0 flex-col gap-2 bg-surface-gray-1 p-4">
		<div class="flex flex-wrap items-center gap-x-4 gap-y-2">
			<h1 class="text-lg font-semibold text-ink-gray-9">{{ heading }}</h1>
			<TabButtons v-model="scope" :buttons="scopeButtons" />
			<label class="flex items-center gap-2 text-sm text-ink-gray-7">
				<input v-model="includeClosed" type="checkbox" class="rounded border-outline-gray-3" />
				{{ __("Include done") }}
			</label>
		</div>
		<p class="text-xs text-ink-gray-5">{{ __("Each report shows how far it is: reported, in GitLab, in progress, testing, done.") }}</p>

		<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-4">{{ error }}</div>

		<div class="flex min-h-0 flex-1 gap-3">
			<section class="min-h-0 min-w-0 flex-1 overflow-y-auto rounded-lg border border-outline-gray-2 bg-surface-white">
				<router-link
					v-for="issue in issues"
					:key="issue.name"
					:to="{ name: 'IssueDetail', params: { implementation, name: issue.name }, query: route.query }"
					class="flex flex-col gap-1 border-b border-outline-gray-1 px-3 py-2 hover:bg-surface-gray-1"
					:class="name === issue.name ? 'bg-surface-gray-2' : ''"
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
			<IssuePanel v-if="name" :key="name" :implementation="implementation" :name="name" class="w-[min(28rem,45%)] shrink-0" @close="closeIssue" />
		</div>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import dayjs from "dayjs"
import { call, TabButtons } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import IssuePanel from "../components/IssuePanel.vue"
import StageLine from "../components/StageLine.vue"
import spaConfig from "../config"

const props = defineProps({
	implementation: { type: String, required: true },
	// set on …/issues/<name> (Phriend links there): the side panel shows that report
	name: { type: String, default: "" },
})

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

// One source per value: Vue compares each, so opening a report (only the route's `name`
// changes) doesn't fetch the list again. A getter returning a new array would fire on every
// route change.
watch([() => props.implementation, () => route.query.scope, () => route.query.route, () => route.query.ref_docname, includeClosed], () => {
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

function closeIssue() {
	router.push({ name: "Issues", params: { implementation: props.implementation }, query: route.query })
}

// Esc closes the side panel.
function onKey(event) {
	if (event.key === "Escape" && props.name) closeIssue()
}
onMounted(() => document.addEventListener("keydown", onKey))
onBeforeUnmount(() => document.removeEventListener("keydown", onKey))
</script>
