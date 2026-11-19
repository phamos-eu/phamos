<template>
	<!-- What phamos builds for this implementation (#1972): the features as a list, a Kanban with the
	     agreed WIP limit, and the work breakdown structure. Customers look; phamos staff move cards. -->
	<div class="h-full min-h-0 overflow-y-auto bg-surface-gray-1 p-5">
		<div class="mx-auto flex max-w-6xl flex-col gap-4">
			<div class="flex flex-wrap items-end justify-between gap-3">
				<div>
					<h1 class="text-lg font-semibold text-ink-gray-9">{{ __("Features") }}</h1>
					<p class="mt-0.5 text-sm text-ink-gray-6">{{ __("What we build for you, how far each part is, and what it takes.") }}</p>
				</div>
				<TabButtons v-model="view" :buttons="viewButtons" />
			</div>

			<MethodNote :summary="note.summary" :details="note.details" />

			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">{{ error }}</div>
			<div v-else-if="loading && !data" class="text-sm text-ink-gray-5">{{ __("Loading…") }}</div>

			<!-- List -->
			<template v-else-if="view === 'list' && data">
				<div class="flex flex-wrap items-center gap-2">
					<select v-model="filters.status" class="rounded border-outline-gray-2 text-sm">
						<option value="">{{ __("All statuses") }}</option>
						<option v-for="s in data.statuses" :key="s" :value="s">{{ __(s) }}</option>
					</select>
					<select v-model="filters.module" class="rounded border-outline-gray-2 text-sm">
						<option value="">{{ __("All modules") }}</option>
						<option v-for="m in modules" :key="m" :value="m">{{ m }}</option>
					</select>
					<select v-model="filters.chapter" class="rounded border-outline-gray-2 text-sm">
						<option value="">{{ __("All chapters") }}</option>
						<option v-for="c in chapters" :key="c.name" :value="c.name">{{ c.label }}</option>
					</select>
				</div>
				<section class="overflow-x-auto rounded-lg border border-outline-gray-2 bg-surface-white">
					<table class="w-full text-sm">
						<thead class="border-b border-outline-gray-2 text-left text-xs text-ink-gray-5">
							<tr>
								<th class="px-4 py-2 font-medium">{{ __("Feature") }}</th>
								<th class="px-3 py-2 font-medium">{{ __("Module") }}</th>
								<th class="px-3 py-2 font-medium">{{ __("Chapter") }}</th>
								<th class="px-3 py-2 font-medium">{{ __("Release") }}</th>
								<th class="px-3 py-2 font-medium">{{ __("Status") }}</th>
								<th class="px-3 py-2 font-medium">{{ __("Level") }}</th>
								<th class="px-3 py-2 text-right font-medium">{{ __("Effort") }}</th>
								<th class="px-3 py-2 font-medium">{{ __("Progress") }}</th>
							</tr>
						</thead>
						<tbody>
							<tr
								v-for="f in filtered"
								:key="f.name"
								class="cursor-pointer border-b border-outline-gray-1 last:border-b-0 hover:bg-surface-gray-1"
								@click="openFeature(f.name)"
							>
								<td class="px-4 py-2.5">
									<div class="font-medium text-ink-gray-9">{{ f.title }}</div>
									<div class="text-xs text-ink-gray-5">{{ f.name }}<template v-if="f.owner_name"> · {{ f.owner_name }}</template></div>
								</td>
								<td class="px-3 py-2.5 text-ink-gray-7">{{ f.module || "—" }}</td>
								<td class="px-3 py-2.5 text-ink-gray-7">{{ f.chapters.map((c) => c.label).join(", ") || "—" }}</td>
								<td class="px-3 py-2.5 text-ink-gray-7">{{ f.releases.map((r) => r.label).join(", ") || "—" }}</td>
								<td class="px-3 py-2.5"><span :class="statusClass(f.status)" class="rounded px-1.5 py-0.5 text-xs">{{ __(f.status) }}</span></td>
								<td class="px-3 py-2.5 text-ink-gray-7">{{ levels(f) }}</td>
								<td class="px-3 py-2.5 text-right text-ink-gray-7">{{ hours(f.effort_hours) }}</td>
								<td class="px-3 py-2.5"><ProgressBar :value="f.progress" /></td>
							</tr>
							<tr v-if="!filtered.length">
								<td colspan="8" class="px-4 py-8 text-center text-ink-gray-5">{{ __("No features here yet.") }}</td>
							</tr>
						</tbody>
					</table>
				</section>
			</template>

			<!-- Kanban -->
			<template v-else-if="view === 'kanban' && data">
				<div class="flex gap-3 overflow-x-auto pb-2">
					<div
						v-for="column in columns"
						:key="column.status"
						class="flex shrink-0 flex-col rounded-lg border bg-surface-white"
						:class="[column.narrow && !expanded[column.status] ? 'w-40' : 'w-64', column.over ? 'border-outline-amber-2 bg-surface-amber-1' : 'border-outline-gray-2', dropTarget === column.status ? 'ring-2 ring-outline-gray-4' : '']"
						@dragover.prevent="data.can_move && (dropTarget = column.status)"
						@dragleave="dropTarget = null"
						@drop.prevent="drop(column.status)"
					>
						<div class="flex items-center justify-between border-b border-outline-gray-1 px-3 py-2">
							<button type="button" class="text-left text-sm font-medium text-ink-gray-8" @click="column.narrow && (expanded[column.status] = !expanded[column.status])">
								{{ __(column.status) }} <span class="text-ink-gray-5">{{ column.cards.length }}</span>
							</button>
							<span v-if="column.limit" class="text-xs" :class="column.over ? 'font-medium text-ink-amber-3' : 'text-ink-gray-5'">
								{{ __("{0} of {1} agreed", [column.cards.length, column.limit]) }}
							</span>
						</div>
						<div v-if="!column.narrow || expanded[column.status]" class="flex min-h-[4rem] flex-col gap-2 p-2">
							<div
								v-for="f in column.cards"
								:key="f.name"
								:draggable="data.can_move"
								class="rounded-md border border-outline-gray-2 bg-surface-white p-2.5 text-sm shadow-sm"
								:class="data.can_move ? 'cursor-grab' : 'cursor-pointer'"
								@dragstart="dragged = f"
								@dragend="dragged = null"
								@click="openFeature(f.name)"
							>
								<div class="font-medium text-ink-gray-9">{{ f.title }}</div>
								<div class="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-ink-gray-6">
									<span v-if="f.module">{{ f.module }}</span>
									<span>{{ hours(f.effort_hours) }}</span>
									<span v-if="f.issues_total">{{ __("{0} of {1} issues open", [f.issues_open, f.issues_total]) }}</span>
									<span v-if="f.oldest_open_days !== null">{{ __("waiting {0} days", [f.oldest_open_days]) }}</span>
									<span v-if="f.touch_hours">{{ __("{0} h worked", [f.touch_hours]) }}</span>
								</div>
								<ProgressBar class="mt-2" :value="f.progress" />
							</div>
						</div>
					</div>
				</div>
				<p v-if="data.wip.over" class="text-sm text-ink-amber-3">
					{{ __("{0} features are in progress, {1} were agreed. Finish one before starting the next.", [data.wip.running, data.wip.limit]) }}
				</p>
			</template>

			<!-- WBS -->
			<template v-else-if="view === 'wbs'">
				<div v-if="!wbs" class="text-sm text-ink-gray-5">{{ __("Loading…") }}</div>
				<section v-else class="rounded-lg border border-outline-gray-2 bg-surface-white p-4">
					<div class="flex flex-wrap items-center justify-between gap-3">
						<div class="flex items-center gap-3">
							<span class="text-sm font-semibold text-ink-gray-9">{{ implementation }}</span>
							<ProgressBar class="w-40" :value="wbs.progress" />
						</div>
						<label class="flex items-center gap-2 text-sm text-ink-gray-7">
							<input v-model="byMilestone" type="checkbox" class="rounded border-outline-gray-3" />
							{{ __("Group issues by GitLab milestone") }}
						</label>
					</div>
					<p class="mt-1 text-xs text-ink-gray-5">
						{{ wbs.weighted ? __("Weighted by estimated hours ({0} h in total).", [wbs.weight_hours]) : __("No hours estimated yet, so every feature counts the same.") }}
					</p>
					<div v-if="!wbs.modules.length" class="py-6 text-center text-sm text-ink-gray-5">{{ __("No features here yet.") }}</div>
					<ul class="mt-3 flex flex-col gap-3">
						<li v-for="m in wbs.modules" :key="m.module" class="rounded-md border border-outline-gray-1">
							<div class="flex items-center gap-3 bg-surface-gray-1 px-3 py-2">
								<span class="flex-1 text-sm font-medium text-ink-gray-8">{{ m.module || __("Without module") }}</span>
								<span class="text-xs text-ink-gray-5">{{ hours(m.weight_hours) }}</span>
								<ProgressBar class="w-32" :value="m.progress" />
							</div>
							<ul class="flex flex-col">
								<li v-for="f in m.features" :key="f.name" class="border-t border-outline-gray-1 px-3 py-2 pl-6">
									<div class="flex items-center gap-3">
										<button type="button" class="flex-1 text-left text-sm text-ink-gray-9 hover:underline" @click="openFeature(f.name)">{{ f.title }}</button>
										<span :class="statusClass(f.status)" class="rounded px-1.5 py-0.5 text-xs">{{ __(f.status) }}</span>
										<span class="w-14 text-right text-xs text-ink-gray-5">{{ hours(f.weight_hours) }}</span>
										<ProgressBar class="w-32" :value="f.progress" />
									</div>
									<div v-for="group in issueGroups(f.issues)" :key="group.label" class="mt-1 pl-4">
										<div v-if="byMilestone" class="text-xs font-medium text-ink-gray-5">{{ group.label }}</div>
										<a
											v-for="i in group.issues"
											:key="i.name"
											:href="i.url"
											target="_blank"
											rel="noopener noreferrer"
											class="flex items-center gap-2 py-0.5 text-xs text-ink-gray-7 hover:text-ink-gray-9"
										>
											<FeatherIcon :name="i.state === 'closed' ? 'check-circle' : 'circle'" class="h-3 w-3" />
											<span class="truncate">#{{ i.issue_id }} {{ i.title }}</span>
											<FeatherIcon name="external-link" class="h-3 w-3 shrink-0" />
										</a>
									</div>
								</li>
							</ul>
						</li>
					</ul>
				</section>
			</template>
		</div>
	</div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call, FeatherIcon, TabButtons } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import MethodNote from "../components/MethodNote.vue"
import ProgressBar from "../components/ProgressBar.vue"
import spaConfig from "../config"

const props = defineProps({ implementation: { type: String, required: true } })

const route = useRoute()
const router = useRouter()

const data = ref(null)
const wbs = ref(null)
const loading = ref(false)
const error = ref("")
const filters = reactive({ status: "", module: "", chapter: "" })
const expanded = reactive({})
const dragged = ref(null)
const dropTarget = ref(null)
const byMilestone = ref(false)

// The view is part of the URL, so a link can open the Kanban or the WBS directly.
const view = computed({
	get: () => (["list", "kanban", "wbs"].includes(route.query.view) ? route.query.view : "list"),
	set: (value) => router.replace({ query: { ...route.query, view: value } }),
})
const viewButtons = [
	{ label: __("List"), value: "list" },
	{ label: __("Kanban"), value: "kanban" },
	{ label: __("Work breakdown"), value: "wbs" },
]

const NOTES = {
	list: {
		summary: __("Every feature with its module, chapter, release, level and effort. Open one to see its definition of done."),
		details: [
			__("A feature is a piece of your system that we build and you use, from the first idea in sales to live use."),
			__("The level shows how far it has come (1 to 6, like the modules), next to the level agreed as the target."),
			__("Effort is the work still open in hours: our estimate, refined by the estimates of its GitLab issues."),
		],
	},
	kanban: {
		summary: __("Features move from left to right. The agreed limit keeps only a few in progress at the same time."),
		details: [
			__("Kanban makes work visible: each card is a feature, each column a step on its way to live use."),
			__("The WIP limit (work in progress) is agreed with you. Fewer things at the same time means each one is finished sooner and waits less."),
			__("When the column turns amber, more features are in progress than agreed: finish one before starting the next."),
		],
	},
	wbs: {
		summary: __("The work breakdown structure splits the implementation into modules, features and GitLab issues."),
		details: [
			__("Breaking the work down shows what the whole consists of, so nothing is forgotten and each part can be estimated."),
			__("Progress adds up from the bottom: a feature counts with its estimated hours, so a big feature moves the total more than a small one."),
			__("A feature is done when its agreed definition of done is met. Until then its progress comes from its closed GitLab issues or its level."),
		],
	},
}
const note = computed(() => NOTES[view.value])

let requestId = 0
watch(() => props.implementation, load, { immediate: true })
watch(view, (value) => value === "wbs" && !wbs.value && loadWbs())

async function load() {
	const id = ++requestId
	loading.value = true
	error.value = ""
	wbs.value = null
	try {
		const result = await call(`${spaConfig.api}.get_features`, { implementation: props.implementation })
		if (id !== requestId) return
		data.value = result
		if (view.value === "wbs") loadWbs()
	} catch (e) {
		if (id === requestId) error.value = e?.messages?.[0] || e?.message || __("Could not load the features")
	} finally {
		if (id === requestId) loading.value = false
	}
}

async function loadWbs() {
	try {
		wbs.value = await call(`${spaConfig.api}.get_wbs`, { implementation: props.implementation })
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not load the work breakdown")
	}
}

const features = computed(() => data.value?.features || [])
const modules = computed(() => [...new Set(features.value.map((f) => f.module).filter(Boolean))].sort())
const chapters = computed(() => {
	const seen = new Map()
	for (const f of features.value) for (const c of f.chapters) seen.set(c.name, c)
	return [...seen.values()]
})
const filtered = computed(() =>
	features.value.filter(
		(f) =>
			(!filters.status || f.status === filters.status) &&
			(!filters.module || f.module === filters.module) &&
			(!filters.chapter || f.chapters.some((c) => c.name === filters.chapter))
	)
)

// Idea and Dropped sit at the edges, collapsed: they are not on the way to live use.
const columns = computed(() =>
	(data.value?.statuses || []).map((status) => {
		const cards = features.value.filter((f) => f.status === status)
		const limit = status === "In Progress" ? data.value.wip.limit : 0
		return { status, cards, limit, over: Boolean(limit && cards.length > limit), narrow: ["Idea", "Dropped"].includes(status) }
	})
)

async function drop(status) {
	dropTarget.value = null
	const feature = dragged.value
	dragged.value = null
	if (!feature || !data.value.can_move || feature.status === status) return
	if (status === "Dropped" && !window.confirm(__("Drop {0}? After the baseline the customer confirms this as a scope change.", [feature.title]))) return
	const before = feature.status
	feature.status = status
	try {
		const result = await call(`${spaConfig.api}.set_feature_status`, { implementation: props.implementation, name: feature.name, status })
		data.value.wip = result.wip
	} catch (e) {
		feature.status = before
		error.value = e?.messages?.[0] || e?.message || __("Could not move the feature")
	}
}

function openFeature(name) {
	router.push({ name: "FeatureDetail", params: { implementation: props.implementation, feature: name }, query: { view: view.value } })
}

function issueGroups(issues) {
	if (!byMilestone.value) return [{ label: "", issues }]
	const groups = new Map()
	for (const i of issues) {
		const label = i.milestone || __("Without milestone")
		if (!groups.has(label)) groups.set(label, [])
		groups.get(label).push(i)
	}
	return [...groups].map(([label, list]) => ({ label, issues: list }))
}

function levels(f) {
	if (!f.target_level && !f.current_level) return "—"
	return `${f.current_level || 0} / ${f.target_level || "—"}`
}

function hours(value) {
	return value ? `${value} h` : "—"
}

function statusClass(status) {
	return {
		Live: "bg-surface-green-2 text-ink-green-4",
		"In Testing": "bg-surface-blue-2 text-ink-blue-3",
		"In Progress": "bg-surface-blue-1 text-ink-blue-3",
		Dropped: "bg-surface-gray-2 text-ink-gray-5 line-through",
	}[status] || "bg-surface-gray-2 text-ink-gray-7"
}
</script>
