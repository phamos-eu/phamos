<template>
	<!-- What phamos builds for this implementation (#1972): the features as a list, a Kanban with the
	     agreed WIP limit, and the work breakdown. Full height, no page scrolling: only a list or a
	     column scrolls inside itself, and a feature opens in a side panel next to it. -->
	<div class="flex h-full min-h-0 flex-col gap-2 bg-surface-gray-1 p-4">
		<header class="flex flex-wrap items-center gap-x-4 gap-y-2">
			<h1 class="text-lg font-semibold text-ink-gray-9">{{ __("Features") }}</h1>
			<TabButtons v-model="view" :buttons="viewButtons" />
			<div v-if="view === 'list' && data" class="flex flex-wrap items-center gap-2">
				<FormControl v-model="filters.status" type="select" size="sm" class="w-36" :options="statusOptions" :aria-label="__('Status')" />
				<FormControl v-model="filters.module" type="select" size="sm" class="w-36" :options="moduleOptions" :aria-label="__('Module')" />
				<FormControl v-model="filters.chapter" type="select" size="sm" class="w-40" :options="chapterOptions" :aria-label="__('Chapter')" />
			</div>
			<div v-if="view === 'kanban' && data" class="flex items-center gap-1.5">
				<button
					v-for="side in sideColumns"
					:key="side.status"
					type="button"
					class="rounded-full border px-2 py-0.5 text-xs"
					:class="[
						expanded[side.status] ? 'border-outline-gray-4 bg-surface-gray-3 text-ink-gray-9' : 'border-outline-gray-2 text-ink-gray-6',
						dropTarget === side.status ? 'ring-2 ring-outline-gray-4' : '',
					]"
					:aria-pressed="!!expanded[side.status]"
					@click="expanded[side.status] = !expanded[side.status]"
					@dragover.prevent="data.can_move && (dropTarget = side.status)"
					@dragleave="dropTarget = null"
					@drop.prevent="drop(side.status)"
				>
					{{ __(side.status) }} {{ side.cards.length }}
				</button>
			</div>
			<label v-if="view === 'wbs'" class="flex items-center gap-2 text-sm text-ink-gray-7">
				<input v-model="byMilestone" type="checkbox" class="rounded border-outline-gray-3" />
				{{ __("Group issues by GitLab milestone") }}
			</label>
			<span v-if="data?.wip.limit" class="ml-auto text-xs" :class="data.wip.over ? 'font-medium text-ink-amber-3' : 'text-ink-gray-5'">
				{{ __("In progress: {0} of {1} agreed", [data.wip.running, data.wip.limit]) }}
			</span>
		</header>
		<MethodNote :summary="note.summary" :details="note.details" />

		<div v-if="error" class="flex items-center gap-2 rounded-lg border border-outline-gray-2 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-4" role="alert">
			<span class="flex-1">{{ error }}</span>
			<button type="button" class="rounded p-0.5 hover:bg-surface-red-2" :aria-label="__('Close')" @click="error = ''">
				<FeatherIcon name="x" class="h-4 w-4" />
			</button>
		</div>

		<div class="flex min-h-0 flex-1 gap-3">
			<div class="flex min-h-0 min-w-0 flex-1 flex-col">
				<div v-if="loading && !data" class="text-sm text-ink-gray-5">{{ __("Loading…") }}</div>

				<!-- List: the table scrolls inside its frame, the header stays. With the side panel open
				     there is less room, so each feature becomes a compact two-line row. -->
				<section v-else-if="view === 'list' && data && selected" class="min-h-0 flex-1 overflow-y-auto rounded-lg border border-outline-gray-2 bg-surface-white">
					<div
						v-for="(f, index) in filtered"
						:key="f.name"
						:ref="(el) => (rows[index] = el)"
						tabindex="0"
						class="cursor-pointer border-b border-outline-gray-1 px-3 py-1.5 last:border-b-0 hover:bg-surface-gray-1 focus:bg-surface-gray-2 focus:outline-none"
						:class="selected === f.name ? 'bg-surface-gray-2' : ''"
						@click="openFeature(f.name)"
						@keydown.enter.prevent="openFeature(f.name)"
						@keydown.down.prevent="focusRow(index + 1)"
						@keydown.up.prevent="focusRow(index - 1)"
					>
						<div class="truncate text-sm font-medium text-ink-gray-9" :title="f.title">{{ f.title }}</div>
						<div class="mt-0.5 flex items-center gap-2 text-xs text-ink-gray-5">
							<StatusBadge :status="f.status" />
							<span class="whitespace-nowrap">{{ levels(f) }}</span>
							<span class="whitespace-nowrap">{{ hours(f.effort_hours) }}</span>
							<ProgressBar class="ml-auto w-24 !min-w-0" :value="f.progress" />
						</div>
					</div>
					<div v-if="!filtered.length" class="px-3 py-8 text-center text-sm text-ink-gray-5">{{ __("No features here yet.") }}</div>
				</section>
				<section v-else-if="view === 'list' && data" class="min-h-0 flex-1 overflow-auto rounded-lg border border-outline-gray-2 bg-surface-white">
					<table class="w-full text-sm">
						<thead class="sticky top-0 z-10 border-b border-outline-gray-2 bg-surface-white text-left text-xs text-ink-gray-5">
							<tr>
								<th class="px-3 py-1.5 font-medium">{{ __("Feature") }}</th>
								<th class="px-2 py-1.5 font-medium">{{ __("Module") }}</th>
								<th class="px-2 py-1.5 font-medium">{{ __("Chapter") }}</th>
								<th class="px-2 py-1.5 font-medium">{{ __("Release") }}</th>
								<th class="px-2 py-1.5 font-medium">{{ __("Status") }}</th>
								<th class="px-2 py-1.5 font-medium">{{ __("Level") }}</th>
								<th class="px-2 py-1.5 text-right font-medium">{{ __("Effort") }}</th>
								<th class="px-2 py-1.5 font-medium">{{ __("Progress") }}</th>
							</tr>
						</thead>
						<tbody>
							<tr
								v-for="(f, index) in filtered"
								:key="f.name"
								:ref="(el) => (rows[index] = el)"
								tabindex="0"
								class="cursor-pointer border-b border-outline-gray-1 last:border-b-0 hover:bg-surface-gray-1 focus:bg-surface-gray-2 focus:outline-none"
								@click="openFeature(f.name)"
								@keydown.enter.prevent="openFeature(f.name)"
								@keydown.down.prevent="focusRow(index + 1)"
								@keydown.up.prevent="focusRow(index - 1)"
							>
								<td class="min-w-[12rem] px-3 py-1.5">
									<div class="font-medium text-ink-gray-9">{{ f.title }}</div>
									<div class="text-xs text-ink-gray-5">{{ f.name }}<template v-if="f.owner_name"> · {{ f.owner_name }}</template></div>
								</td>
								<td class="px-2 py-1.5 text-ink-gray-7">{{ f.module || "—" }}</td>
								<td class="px-2 py-1.5 text-ink-gray-7">{{ f.chapters.map((c) => c.label).join(", ") || "—" }}</td>
								<td class="px-2 py-1.5 text-ink-gray-7">{{ f.releases.map((r) => r.label).join(", ") || "—" }}</td>
								<td class="px-2 py-1.5"><StatusBadge :status="f.status" /></td>
								<td class="whitespace-nowrap px-2 py-1.5 text-ink-gray-7">{{ levels(f) }}</td>
								<td class="whitespace-nowrap px-2 py-1.5 text-right text-ink-gray-7">{{ hours(f.effort_hours) }}</td>
								<td class="px-2 py-1.5"><ProgressBar class="w-28" :value="f.progress" /></td>
							</tr>
							<tr v-if="!filtered.length">
								<td colspan="8" class="px-3 py-8 text-center text-ink-gray-5">{{ __("No features here yet.") }}</td>
							</tr>
						</tbody>
					</table>
				</section>

				<!-- Kanban: the columns share the width and scroll on their own -->
				<div v-else-if="view === 'kanban' && data" class="flex min-h-0 flex-1 gap-2">
					<div
						v-for="column in visibleColumns"
						:key="column.status"
						class="flex min-h-0 flex-col rounded-lg border bg-surface-white"
						:class="[
							'min-w-0 flex-1',
							column.over ? 'border-outline-amber-2 bg-surface-amber-1' : 'border-outline-gray-2',
							dropTarget === column.status ? 'ring-2 ring-outline-gray-4' : '',
						]"
						@dragover.prevent="data.can_move && (dropTarget = column.status)"
						@dragleave="dropTarget = null"
						@drop.prevent="drop(column.status)"
					>
						<div class="flex items-center justify-between gap-2 border-b border-outline-gray-1 px-2.5 py-1.5">
							<span class="truncate text-sm font-medium text-ink-gray-8" :title="__(column.status)">{{ __(column.status) }}</span>
							<span class="shrink-0 text-xs" :class="column.over ? 'font-medium text-ink-amber-3' : 'text-ink-gray-5'">
								{{ column.limit ? `${column.cards.length}/${column.limit}` : column.cards.length }}
							</span>
						</div>
						<div class="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto p-1.5">
							<div
								v-for="f in column.cards"
								:key="f.name"
								:draggable="data.can_move"
								tabindex="0"
								class="rounded-md border border-outline-gray-2 bg-surface-white px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-outline-gray-4"
								:class="[data.can_move ? 'cursor-grab' : 'cursor-pointer', selected === f.name ? 'ring-2 ring-outline-gray-4' : '']"
								@dragstart="dragged = f"
								@dragend="dragged = null"
								@click="openFeature(f.name)"
								@keydown.enter.prevent="openFeature(f.name)"
							>
								<div class="line-clamp-2 font-medium leading-snug text-ink-gray-9">{{ f.title }}</div>
								<div class="mt-0.5 flex flex-wrap gap-x-2 text-xs text-ink-gray-5">
									<span>{{ hours(f.effort_hours) }}</span>
									<span v-if="f.issues_total">{{ __("{0}/{1} open", [f.issues_open, f.issues_total]) }}</span>
									<span v-if="f.oldest_open_days !== null">{{ __("{0} d waiting", [f.oldest_open_days]) }}</span>
								</div>
								<ProgressBar class="mt-1" :value="f.progress" />
							</div>
						</div>
					</div>
				</div>

				<!-- Work breakdown: modules side by side when there is room; issues fold out per feature -->
				<template v-else-if="view === 'wbs'">
					<div v-if="!wbs" class="text-sm text-ink-gray-5">{{ __("Loading…") }}</div>
					<div v-else class="flex min-h-0 flex-1 flex-col gap-2">
						<div class="flex flex-wrap items-center gap-3 rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2">
							<span class="text-sm font-semibold text-ink-gray-9">{{ implementation }}</span>
							<ProgressBar class="w-48" :value="wbs.progress" />
							<span class="text-xs text-ink-gray-5">
								{{ wbs.weighted ? __("Weighted by estimated hours ({0} h in total).", [wbs.weight_hours]) : __("No hours estimated yet, so every feature counts the same.") }}
							</span>
						</div>
						<div v-if="!wbs.modules.length" class="py-6 text-center text-sm text-ink-gray-5">{{ __("No features here yet.") }}</div>
						<div class="grid min-h-0 flex-1 auto-rows-min gap-2 overflow-y-auto" :class="selected ? 'grid-cols-1' : 'grid-cols-[repeat(auto-fit,minmax(22rem,1fr))]'">
							<section v-for="m in wbs.modules" :key="m.module" class="rounded-lg border border-outline-gray-2 bg-surface-white">
								<div class="flex items-center gap-2 border-b border-outline-gray-1 px-3 py-1.5">
									<span class="flex-1 truncate text-sm font-medium text-ink-gray-8">{{ m.module || __("Without module") }}</span>
									<span class="text-xs text-ink-gray-5">{{ hours(m.weight_hours) }}</span>
									<ProgressBar class="w-28" :value="m.progress" />
								</div>
								<ul>
									<li v-for="f in m.features" :key="f.name" class="border-b border-outline-gray-1 px-3 py-1 last:border-b-0">
										<div class="flex items-center gap-2">
											<button
												v-if="f.issues.length"
												type="button"
												class="text-ink-gray-5 hover:text-ink-gray-9"
												:aria-expanded="!!openIssues[f.name]"
												:aria-label="__('Show issues')"
												@click="openIssues[f.name] = !openIssues[f.name]"
											>
												<FeatherIcon :name="openIssues[f.name] ? 'chevron-down' : 'chevron-right'" class="h-3.5 w-3.5" />
											</button>
											<span v-else class="w-3.5" />
											<button type="button" class="min-w-0 flex-1 truncate text-left text-sm text-ink-gray-9 hover:underline" @click="openFeature(f.name)">{{ f.title }}</button>
											<span v-if="f.issues.length" class="text-xs text-ink-gray-5">{{ f.issues.length }}</span>
											<span class="w-12 text-right text-xs text-ink-gray-5">{{ hours(f.weight_hours) }}</span>
											<ProgressBar class="w-24" :value="f.progress" />
										</div>
										<div v-if="openIssues[f.name]" class="pb-1 pl-6">
											<div v-for="group in issueGroups(f.issues)" :key="group.label">
												<div v-if="byMilestone" class="mt-1 text-xs font-medium text-ink-gray-5">{{ group.label }}</div>
												<a
													v-for="i in group.issues"
													:key="i.name"
													:href="i.url"
													target="_blank"
													rel="noopener noreferrer"
													class="flex items-center gap-2 py-0.5 text-xs text-ink-gray-7 hover:text-ink-gray-9"
												>
													<FeatherIcon :name="i.state === 'closed' ? 'check-circle' : 'circle'" class="h-3 w-3 shrink-0" />
													<span class="truncate">#{{ i.issue_id }} {{ i.title }}</span>
													<FeatherIcon name="external-link" class="h-3 w-3 shrink-0" />
												</a>
											</div>
										</div>
									</li>
								</ul>
							</section>
						</div>
					</div>
				</template>
			</div>

			<!-- Feature detail beside the list or board, not on a page of its own -->
			<FeaturePanel
				v-if="selected"
				:key="`${selected}-${refreshKey}`"
				:implementation="implementation"
				:feature="selected"
				class="w-[min(28rem,45%)] shrink-0"
				@close="closeFeature"
			/>
		</div>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call, FeatherIcon, FormControl, TabButtons } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import FeaturePanel from "../components/FeaturePanel.vue"
import MethodNote from "../components/MethodNote.vue"
import ProgressBar from "../components/ProgressBar.vue"
import StatusBadge from "../components/StatusBadge.vue"
import spaConfig from "../config"

const props = defineProps({
	implementation: { type: String, required: true },
	// set on …/features/<feature>: the side panel shows that feature
	feature: { type: String, default: "" },
})

const route = useRoute()
const router = useRouter()

const data = ref(null)
const wbs = ref(null)
const loading = ref(false)
const error = ref("")
const filters = reactive({ status: "", module: "", chapter: "" })
const expanded = reactive({})
const openIssues = reactive({})
const dragged = ref(null)
const dropTarget = ref(null)
const byMilestone = ref(false)
// bumped after a move, so an open side panel reloads its status and history
const refreshKey = ref(0)
const rows = []

const selected = computed(() => props.feature || "")

// The view is part of the URL, so a link can open the Kanban or the work breakdown directly.
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

async function load({ quiet = false } = {}) {
	const id = ++requestId
	loading.value = !quiet
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
const statusOptions = computed(() => [
	{ label: __("All statuses"), value: "" },
	...(data.value?.statuses || []).map((s) => ({ label: __(s), value: s })),
])
const moduleOptions = computed(() => [{ label: __("All modules"), value: "" }, ...modules.value.map((m) => ({ label: m, value: m }))])
const chapterOptions = computed(() => [
	{ label: __("All chapters"), value: "" },
	...chapters.value.map((c) => ({ label: c.label, value: c.name })),
])
const filtered = computed(() =>
	features.value.filter(
		(f) =>
			(!filters.status || f.status === filters.status) &&
			(!filters.module || f.module === filters.module) &&
			(!filters.chapter || f.chapters.some((c) => c.name === filters.chapter))
	)
)

// Idea and Dropped are not on the way to live use: they sit as chips in the header (still drop
// targets) and join the board as a column only when opened, so the main columns always fit.
const SIDE_STATUSES = ["Idea", "Dropped"]
const columns = computed(() =>
	(data.value?.statuses || []).map((status) => {
		const cards = features.value.filter((f) => f.status === status)
		const limit = status === "In Progress" ? data.value.wip.limit : 0
		return { status, cards, limit, over: Boolean(limit && cards.length > limit), side: SIDE_STATUSES.includes(status) }
	})
)
const sideColumns = computed(() => columns.value.filter((c) => c.side))
const visibleColumns = computed(() => columns.value.filter((c) => !c.side || expanded[c.status]))

async function drop(status) {
	dropTarget.value = null
	const feature = dragged.value
	dragged.value = null
	if (!feature || !data.value.can_move || feature.status === status) return
	if (status === "Dropped" && !window.confirm(__("Drop {0}? After the baseline the customer confirms this as a scope change.", [feature.title]))) return
	const before = feature.status
	feature.status = status
	try {
		await call(`${spaConfig.api}.set_feature_status`, { implementation: props.implementation, name: feature.name, status })
		// progress, the WIP figure and the work breakdown come from the server: fetch them again
		await load({ quiet: true })
		refreshKey.value += 1
	} catch (e) {
		feature.status = before
		error.value = e?.messages?.[0] || e?.message || __("Could not move the feature")
	}
}

function openFeature(name) {
	router.push({ name: "FeatureDetail", params: { implementation: props.implementation, feature: name }, query: route.query })
}

function closeFeature() {
	router.push({ name: "Features", params: { implementation: props.implementation }, query: route.query })
}

function focusRow(index) {
	rows[Math.max(0, Math.min(index, filtered.value.length - 1))]?.focus()
}

// Esc closes the side panel; an open "Learn more" popover closes first (MethodNote).
function onKey(event) {
	if (event.key === "Escape" && selected.value && !document.querySelector("[role=dialog]")) closeFeature()
}
onMounted(() => document.addEventListener("keydown", onKey, true))
onBeforeUnmount(() => document.removeEventListener("keydown", onKey, true))

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
</script>
