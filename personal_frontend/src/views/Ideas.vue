<template>
	<div class="flex h-full min-h-0 bg-surface-gray-1">
		<div class="h-full min-h-0 flex-1 overflow-y-auto p-5">
			<div class="mx-auto flex max-w-4xl flex-col gap-5">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div>
						<h1 class="text-lg font-semibold text-ink-gray-9">{{ __("Ideas") }}</h1>
						<p class="text-sm text-ink-gray-6">{{ __("Catch rough thoughts here. Open one when you want to write it out.") }}</p>
					</div>
					<Button variant="solid" :loading="creating" @click="newIdea">
						<template #prefix><FeatherIcon name="plus" class="h-4 w-4" /></template>
						{{ __("New idea") }}
					</Button>
				</div>

				<div v-if="ideas.error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
					{{ ideas.error }}
				</div>
				<div v-else-if="!ideas.loaded" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
					{{ __("Loading your ideas…") }}
				</div>
				<section v-else class="rounded-lg border border-outline-gray-2 bg-surface-white">
					<div class="flex flex-wrap items-center justify-between gap-3 border-b border-outline-gray-1 px-4 py-3">
						<TabButtons v-model="stageFilter" :buttons="stageButtons" />
						<label class="flex items-center gap-2 text-sm text-ink-gray-7">
							<input v-model="ideas.showClosed" type="checkbox" @change="loadIdeas" />
							{{ __("Show harvested and composted") }}
						</label>
					</div>
					<div v-if="!rows.length" class="flex flex-col items-center gap-3 px-4 py-10 text-center">
						<p class="text-sm text-ink-gray-5">
							{{ stageFilter ? __("No idea in this stage.") : __("No ideas yet. A short name is enough to start.") }}
						</p>
						<Button v-if="!stageFilter" variant="subtle" @click="newIdea">{{ __("New idea") }}</Button>
					</div>
					<ul v-else class="divide-y divide-outline-gray-1">
						<li v-for="row in rows" :key="row.name">
							<router-link
								:to="{ name: 'IdeaDetail', params: { name: row.name } }"
								data-list-item
								class="flex flex-col gap-2 px-4 py-3 hover:bg-surface-gray-1 focus:outline-none focus-visible:bg-surface-gray-2"
							>
								<div class="flex items-start justify-between gap-3">
									<span class="min-w-0 flex-1 truncate text-sm font-medium text-ink-gray-9">{{ row.title }}</span>
									<Badge :theme="STAGE_THEMES[row.stage] || 'gray'" size="sm">{{ __(row.stage) }}</Badge>
								</div>
								<p class="line-clamp-2 text-sm text-ink-gray-5">{{ row.summary || __("No notes yet") }}</p>
								<StageSteps
									size="compact"
									:steps="steps"
									:current="row.stage"
									:dimmed="row.stage === 'Compost'"
								/>
								<div class="flex flex-wrap gap-x-3 text-xs text-ink-gray-5">
									<span>{{ ageLabel(row.age_days) }}</span>
									<span v-if="row.children_count">{{ __("{0} ideas came out of it", [row.children_count]) }}</span>
									<span v-if="row.spawned_from_title">{{ __("from {0}", [row.spawned_from_title]) }}</span>
								</div>
							</router-link>
						</li>
					</ul>
				</section>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Badge, TabButtons } from "frappe-ui"
import StageSteps from "@spa/components/StageSteps.vue"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { __ } from "@spa/utils/i18n.js"
import { notify } from "@spa/utils/notify.js"
import { STAGE_THEMES, ageLabel, createIdea, ideas, loadIdeaOptions, loadIdeas, stageSteps } from "../ideasStore.js"

const route = useRoute()
const router = useRouter()
const stageFilter = ref("")
const creating = ref(false)

const steps = computed(() => stageSteps())
const stageButtons = computed(() => [
	{ label: __("All"), value: "" },
	...(ideas.options?.stages || [])
		.filter((s) => ideas.showClosed || !(ideas.options?.closed_stages || []).includes(s))
		.map((s) => ({ label: __(s), value: s })),
])
const rows = computed(() => (stageFilter.value ? ideas.rows.filter((r) => r.stage === stageFilter.value) : ideas.rows))

useUserRealtime("cockpit_idea_changed", loadIdeas, { debounceMs: 300 })

async function newIdea() {
	if (creating.value) return
	creating.value = true
	try {
		const doc = await createIdea()
		notify.success(__("Idea captured"))
		router.push({ name: "IdeaDetail", params: { name: doc.name }, query: { fresh: 1 } })
	} catch (e) {
		notify.error(__("Could not create the idea"), e?.messages?.[0] || e?.message || "")
	} finally {
		creating.value = false
	}
}

// "Idea" in the Create menu arrives as ?new=1.
function openFromQuery() {
	if (!route.query.new) return
	router.replace({ query: {} })
	newIdea()
}

watch(
	() => ideas.showClosed,
	(show) => {
		if (!show && (ideas.options?.closed_stages || []).includes(stageFilter.value)) stageFilter.value = ""
	}
)

onMounted(() => {
	loadIdeaOptions()
	loadIdeas()
	openFromQuery()
})
watch(() => route.query.new, openFromQuery)
</script>
