<template>
	<!-- The Roadmap (#2035, replaces the Planning placeholder): when each module reaches which
	     depth level, drawn by RoadmapGantt (#2034) from get_roadmap (#2033). Full height, no page
	     scrolling: the timeline scrolls inside itself, and a chapter, a feature or a stack of
	     features opens in a side panel next to it. Read-only; date changes are proposed in Desk. -->
	<div class="flex h-full min-h-0 flex-col gap-2 bg-surface-gray-1 p-4">
		<header class="flex flex-wrap items-center gap-x-4 gap-y-2">
			<h1 class="text-lg font-semibold text-ink-gray-9">{{ __("Roadmap") }}</h1>
			<MethodNote class="min-w-[12rem] flex-1" :summary="note.summary" :details="note.details" />
			<TabButtons v-model="zoom" :buttons="zoomButtons" />
			<label v-if="data?.baseline" class="flex items-center gap-2 text-sm text-ink-gray-7">
				<input v-model="showBaseline" type="checkbox" class="rounded border-outline-gray-3" />
				{{ __("Compare with baseline") }}
			</label>
			<span v-else-if="data" class="text-xs text-ink-gray-5">{{ __("A baseline is set when the Planning meeting is submitted.") }}</span>
		</header>

		<div v-if="error" class="flex items-center gap-2 rounded-lg border border-outline-gray-2 bg-surface-red-1 px-3 py-2 text-sm text-ink-red-4" role="alert">
			<span class="flex-1">{{ error }}</span>
			<button type="button" class="rounded p-0.5 hover:bg-surface-red-2" :aria-label="__('Close')" @click="error = ''">
				<FeatherIcon name="x" class="h-4 w-4" />
			</button>
		</div>

		<div class="flex min-h-0 flex-1 gap-3">
			<div class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-white">
				<div v-if="loading && !data" class="p-4 text-sm text-ink-gray-5">{{ __("Loading…") }}</div>
				<div v-else-if="data && !gantt.rows.length" class="flex flex-1 items-center justify-center p-6 text-center text-sm text-ink-gray-5">
					{{ __("Nothing planned yet. Chapters and modules are planned in Desk, on the Implementation.") }}
				</div>
				<RoadmapGantt
					v-else-if="data"
					:rows="gantt.rows"
					:dependencies="gantt.dependencies"
					:markers="gantt.markers"
					:range="data.range"
					:zoom="zoom"
					:show-baseline="showBaseline && Boolean(data.baseline)"
					:selected="ganttSelected"
					@select="onSelect"
				/>
			</div>

			<ChapterPanel
				v-if="selection?.type === 'bar' && selectedBar"
				:key="selectedBar.name"
				:implementation="implementation"
				:bar="selectedBar"
				:links="selectedLinks"
				:features="selectedFeatures"
				:features-error="featuresError"
				:can-propose="Boolean(data?.can_propose)"
				class="w-[min(26rem,45%)] shrink-0"
				@close="selection = null"
				@select-chapter="(name) => (selection = { type: 'bar', name })"
				@open-feature="openFeature"
			/>
			<FeatureStackPanel
				v-else-if="selection?.type === 'stack'"
				:features="stackList"
				class="w-[min(26rem,45%)] shrink-0"
				@close="selection = null"
				@open-feature="openFeature"
			/>
			<FeaturePanel
				v-else-if="selection?.type === 'event'"
				:key="selection.name"
				:implementation="implementation"
				:feature="selection.name"
				class="w-[min(28rem,45%)] shrink-0"
				@close="selection = null"
			/>
		</div>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"
import { call, FeatherIcon, TabButtons } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import RoadmapGantt from "@spa/components/RoadmapGantt.vue"
import ChapterPanel from "../components/ChapterPanel.vue"
import FeaturePanel from "../components/FeaturePanel.vue"
import FeatureStackPanel from "../components/FeatureStackPanel.vue"
import MethodNote from "../components/MethodNote.vue"
import spaConfig from "../config"
import { barsByName, chapterLinks, ganttData, loadPrefs, savePrefs, stackFeatures } from "../utils/roadmapView.js"

const props = defineProps({
	implementation: { type: String, required: true },
})

const data = ref(null)
const loading = ref(false)
const error = ref("")
// { type: "bar", name } | { type: "event", name } | { type: "stack", names }
const selection = ref(null)
// get_features, read once when the first chapter panel opens: a chapter's features
const features = ref(null)
const featuresRequested = ref(false)
const featuresError = ref("")

// --- Zoom and baseline toggle, remembered per viewer (#1694 decisions 2 and 4) -------------

function storage() {
	try {
		return window.localStorage
	} catch (e) {
		return null
	}
}
const prefs = reactive(loadPrefs(storage()))
const zoom = computed({
	get: () => prefs.zoom,
	set: (value) => (prefs.zoom = value),
})
const showBaseline = computed({
	get: () => prefs.showBaseline,
	set: (value) => (prefs.showBaseline = value),
})
watch(prefs, () => savePrefs(storage(), prefs))

const zoomButtons = [
	{ label: __("Weeks"), value: "week" },
	{ label: __("Months"), value: "month" },
	{ label: __("Quarters"), value: "quarter" },
]

const note = {
	summary: __("The roadmap shows when each module reaches which depth level, and which chapters decide the end date."),
	details: [
		__("Each row is a module. A bar is a chapter: the work that takes the module from one level to the next. Levels 1 to 6 say how deep the module is in use, from first steps to fully running."),
		__("The critical path is the chain of chapters that decides the end date. Its bars have a red border: if one of them is late, the end date moves."),
		__("Slack is how many days a chapter can slip before it delays the end date. Late means it already does."),
		__("The baseline is the plan agreed in the Planning meeting. With “Compare with baseline” on, a thin bar under each chapter shows that plan, and “+5 d” how far the date has moved since."),
		__("Dots are features: ○ planned, ● finished. Diamonds are GitLab milestones and releases."),
	],
}

// --- Data -----------------------------------------------------------------------------------

let requestId = 0
watch(
	() => props.implementation,
	() => {
		// the page stays mounted when the implementation changes: drop the old one's data first
		data.value = null
		selection.value = null
		features.value = null
		featuresError.value = ""
		featuresRequested.value = false
		load()
	},
	{ immediate: true }
)

async function load() {
	const id = ++requestId
	loading.value = true
	error.value = ""
	try {
		const result = await call(`${spaConfig.api}.get_roadmap`, { implementation: props.implementation })
		if (id === requestId) data.value = result
	} catch (e) {
		if (id === requestId) error.value = e?.messages?.[0] || e?.message || __("Could not load the roadmap")
	} finally {
		if (id === requestId) loading.value = false
	}
}

async function loadFeatures() {
	featuresRequested.value = true
	featuresError.value = ""
	const id = requestId
	try {
		const result = await call(`${spaConfig.api}.get_features`, { implementation: props.implementation })
		if (id === requestId) features.value = result.features || []
	} catch (e) {
		if (id === requestId) {
			// the next chapter panel tries again
			featuresRequested.value = false
			featuresError.value = e?.messages?.[0] || e?.message || __("Could not load the features")
		}
	}
}

const gantt = computed(() => ganttData(data.value, __))
const bars = computed(() => barsByName(data.value))

// --- Selection and side panel -------------------------------------------------------------

const selectedBar = computed(() => (selection.value?.type === "bar" ? bars.value.get(selection.value.name) : null))
const selectedLinks = computed(() => chapterLinks(data.value, selection.value?.name))
const stackList = computed(() => (selection.value?.type === "stack" ? stackFeatures(data.value, selection.value.names) : []))

// The first chapter panel loads the features; null while they load.
watch(
	() => selectedBar.value?.chapter,
	(chapter) => chapter && !featuresRequested.value && features.value === null && loadFeatures()
)
const selectedFeatures = computed(() => {
	const chapter = selectedBar.value?.chapter
	if (!chapter) return []
	if (features.value === null) return null
	return features.value.filter((f) => f.chapters.some((c) => c.name === chapter))
})

// What RoadmapGantt highlights: a stack shows as selected through its first feature.
const ganttSelected = computed(() => {
	const s = selection.value
	if (!s) return null
	if (s.type === "stack") return { type: "event", name: s.names[0] }
	return { type: s.type, name: s.name }
})

function onSelect(selected) {
	if (!selected) selection.value = null
	else if (selected.names?.length > 1) selection.value = { type: "stack", names: selected.names }
	else selection.value = { type: selected.type, name: selected.name }
}

function openFeature(name) {
	selection.value = { type: "event", name }
}

// Esc closes the side panel; an open "Learn more" popover closes first (MethodNote).
function onKey(event) {
	if (event.key === "Escape" && selection.value && !document.querySelector("[role=dialog]")) selection.value = null
}
onMounted(() => document.addEventListener("keydown", onKey, true))
onBeforeUnmount(() => document.removeEventListener("keydown", onKey, true))
</script>
