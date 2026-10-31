<template>
	<div class="flex h-full min-h-0 bg-surface-gray-1">
		<div class="h-full min-h-0 flex-1 overflow-y-auto p-5">
			<div class="flex flex-col gap-5">
				<!-- The page title ("My Ideas") is in the cockpit header; no second heading here. -->
				<div class="flex flex-wrap items-center justify-between gap-3">
					<p class="text-sm text-ink-gray-6">{{ __("Catch rough thoughts here. Open one when you want to write it out.") }}</p>
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
					<div class="border-b border-outline-gray-1 px-4 py-3">
						<!-- TabButtons' look and keys, with a stage icon in front of each stage (TabButtons takes
						     Feather icon names only). -->
						<RadioGroup v-model="stageFilter" :aria-label="__('Stage')">
							<div class="flex flex-wrap gap-0.5 rounded bg-surface-gray-2 p-0.5 text-sm">
								<RadioGroupOption
									v-for="button in stageButtons"
									:key="button.value"
									v-slot="{ active, checked }"
									as="template"
									:value="button.value"
								>
									<button
										type="button"
										:class="[
											active ? 'ring-outline-gray-2 focus-visible:ring' : '',
											checked ? 'bg-surface-white text-ink-gray-9 shadow' : 'text-ink-gray-7',
											'flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-[7px] px-2 py-[5px] leading-none transition-colors focus:outline-none',
										]"
									>
										<StageIcon v-if="button.value" :name="button.value" class="h-3.5 w-3.5 shrink-0" />
										<RadioGroupLabel as="span">{{ button.label }}</RadioGroupLabel>
									</button>
								</RadioGroupOption>
							</div>
						</RadioGroup>
					</div>
					<p v-if="!rows.length" class="px-4 py-10 text-center text-sm text-ink-gray-5">
						{{ stageFilter ? __("No idea in this stage.") : __("No ideas yet. A short name is enough to start.") }}
					</p>
					<ul v-else class="divide-y divide-outline-gray-1">
						<li v-for="row in rows" :key="row.name">
							<router-link
								:to="{ name: 'IdeaDetail', params: { name: row.name } }"
								data-list-item
								class="flex flex-col gap-2 px-4 py-3 hover:bg-surface-gray-1 focus:outline-none focus-visible:bg-surface-gray-2"
							>
								<span class="truncate text-sm font-medium text-ink-gray-9">{{ row.title }}</span>
								<p v-if="excerpt(row)" class="line-clamp-2 text-sm text-ink-gray-5">{{ excerpt(row) }}</p>
								<!-- One info line; the stage as a word only (icons live in the tabs above). -->
								<div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-gray-5">
									<span>{{ ageLabel(row.age_days) }}</span>
									<span v-if="row.children_count">
										{{ row.children_count === 1 ? __("1 idea came out of it") : __("{0} ideas came out of it", [row.children_count]) }}
									</span>
									<span v-if="row.spawned_from_title">{{ __("from {0}", [row.spawned_from_title]) }}</span>
									<span class="ml-auto whitespace-nowrap text-ink-gray-6">{{ __(row.stage) }}</span>
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
import { RadioGroup, RadioGroupLabel, RadioGroupOption } from "@headlessui/vue"
import StageIcon from "@spa/components/StageIcon.vue"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { __ } from "@spa/utils/i18n.js"
import { summaryWithoutTitle } from "@spa/utils/ideaSummary.js"
import { notify } from "@spa/utils/notify.js"
import { ageLabel, createIdea, ideas, loadIdeaOptions, loadIdeas } from "../ideasStore.js"

const route = useRoute()
const router = useRouter()
const stageFilter = ref("")
const creating = ref(false)

// One control for both: "Open" and the open stages filter the list; Harvest and Compost load the
// closed ideas (they replace the former "Show harvested and composted" checkbox).
const stageButtons = computed(() => [
	{ label: __("Open"), value: "" },
	...(ideas.options?.stages || []).map((s) => ({ label: __(s), value: s })),
])
const excerpt = (row) => summaryWithoutTitle(row.summary, row.title)
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

watch(stageFilter, (stage) => {
	const closed = (ideas.options?.closed_stages || []).includes(stage)
	if (closed !== ideas.showClosed) {
		ideas.showClosed = closed
		loadIdeas()
	}
})

onMounted(() => {
	loadIdeaOptions()
	loadIdeas()
	openFromQuery()
})
watch(() => route.query.new, openFromQuery)
</script>
