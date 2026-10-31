<template>
	<div class="flex h-full min-h-0 bg-surface-gray-1">
		<div class="h-full min-h-0 flex-1 overflow-y-auto p-5">
			<div class="flex flex-col gap-4">
				<!-- Back to the list is the active "Ideas" entry in the sidebar; only the parent link stays. -->
				<router-link
					v-if="idea?.spawned_from"
					:to="{ name: 'IdeaDetail', params: { name: idea.spawned_from } }"
					class="self-start text-xs text-ink-gray-5 hover:text-ink-gray-8"
				>
					{{ __("Came from") }} <span class="font-medium text-ink-gray-7">{{ idea.spawned_from_title }}</span>
				</router-link>

				<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
					{{ error }}
				</div>
				<div v-else-if="!idea" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
					{{ __("Loading the idea…") }}
				</div>
				<template v-else>
					<div class="flex flex-wrap items-start justify-between gap-3">
						<input
							ref="titleInput"
							v-model="autosave.draft.title"
							class="min-w-0 flex-1 border-0 bg-transparent px-0 py-1 text-2xl font-semibold tracking-tight text-ink-gray-9 outline-none focus:ring-0"
							:placeholder="__('Give this idea a short name')"
							@focus="autosave.setFocused('title', true)"
							@blur="onTitleBlur"
							@keydown.esc.prevent="autosave.revert('title')"
							@keydown.enter.prevent="$event.target.blur()"
						/>
						<div class="flex items-center gap-3 pt-2">
							<DocSyncBanner :autosave="autosave" />
							<Button v-if="!closed" variant="solid" @click="startWriting">
								<template #prefix><FeatherIcon name="edit-3" class="h-4 w-4" /></template>
								{{ __("Start writing") }}
							</Button>
						</div>
					</div>

					<div class="flex flex-col gap-1.5">
						<StageSteps
							:steps="steps"
							:current="autosave.draft.stage"
							clickable
							icons
							:dimmed="composted"
							:aria-label="__('Stage')"
							@select="setStage"
						/>
						<div class="flex flex-wrap items-center justify-between gap-2 text-xs">
							<span class="text-ink-gray-6">
								<Badge v-if="composted" theme="gray" size="sm" class="mr-1">
									<template #prefix><StageIcon name="Compost" class="h-3 w-3" /></template>
									{{ __("Compost") }}
								</Badge>
								{{ stageJob(autosave.draft.stage) }}
							</span>
							<button v-if="composted" type="button" class="text-ink-gray-6 underline-offset-2 hover:underline" @click="setStage('Seed')">
								{{ __("Take it up again") }}
							</button>
							<button v-else type="button" class="text-ink-gray-5 underline-offset-2 hover:text-ink-gray-8 hover:underline" @click="compost">
								{{ __("Compost this idea") }}
							</button>
						</div>
					</div>

					<div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_16rem]">
						<section class="min-h-[24rem] rounded-lg border border-outline-gray-2 bg-surface-white p-4">
							<RichTextField
								:key="idea.name"
								v-model="autosave.draft.content"
								:placeholder="__('Dump everything about this idea here…')"
								editor-class="prose-sm min-h-[20rem] max-w-none"
								:field-label="__('Content')"
								@focus="autosave.setFocused('content', true)"
								@blur="onContentBlur"
							/>
						</section>

						<aside class="flex flex-col gap-4">
							<div v-if="idea.last_session" class="rounded-lg border border-outline-gray-2 bg-surface-white p-3 text-xs text-ink-gray-6">
								<div class="mb-0.5 text-sm font-medium text-ink-gray-9">{{ __("Writing") }}</div>
								{{ __("Last session: {0} words, {1}", [idea.last_session.words_written, formatDatetime(idea.last_session.started_on)]) }}
								<div v-if="idea.sessions_count > 1">{{ __("{0} sessions so far", [idea.sessions_count]) }}</div>
							</div>
							<div class="rounded-lg border border-outline-gray-2 bg-surface-white p-3">
								<div class="mb-1 text-sm font-medium text-ink-gray-9">{{ __("Ideas that came out of this one") }}</div>
								<p v-if="!idea.children.length" class="mb-2 text-xs text-ink-gray-5">
									{{ __("Side thoughts you capture here or while writing show up as their own ideas.") }}
								</p>
								<ul v-else class="mb-2 flex flex-col gap-1">
									<li v-for="child in idea.children" :key="child.name">
										<router-link
											:to="{ name: 'IdeaDetail', params: { name: child.name } }"
											class="flex items-center justify-between gap-2 rounded px-1.5 py-1 text-sm text-ink-gray-8 hover:bg-surface-gray-2"
										>
											<span class="truncate">{{ child.title }}</span>
											<span class="shrink-0 text-xs text-ink-gray-5">{{ __(child.stage) }}</span>
										</router-link>
									</li>
								</ul>
								<Button class="w-full" variant="subtle" @click="openSideIdea">
									<template #prefix><FeatherIcon name="plus" class="h-3.5 w-3.5" /></template>
									{{ __("Add idea") }}
								</Button>
							</div>
							<div class="flex flex-col gap-1 px-1 text-xs text-ink-gray-5">
								<span>{{ ageLabel(idea.age_days) }}</span>
								<a :href="deskRecordUrl('Idea', idea.name)" target="_blank" rel="noopener" class="hover:text-ink-gray-8">
									{{ __("History in Desk") }}
								</a>
							</div>
						</aside>
					</div>
				</template>
			</div>
		</div>

		<Dialog v-model="sideOpen" :options="{ title: __('Add an idea that came out of this one') }">
			<template #body-content>
				<p class="mb-2 text-xs text-ink-gray-5">{{ __("The first line becomes its title.") }}</p>
				<textarea
					ref="sideInput"
					v-model="sideText"
					rows="6"
					class="w-full resize-none rounded border border-outline-gray-2 bg-surface-white p-2 text-sm text-ink-gray-8"
					:placeholder="__('Write your thought…')"
				/>
			</template>
			<template #actions>
				<div class="flex justify-end gap-2">
					<Button variant="subtle" @click="sideOpen = false">{{ __("Cancel") }}</Button>
					<Button variant="solid" :disabled="!sideText.trim()" :loading="sideSaving" @click="saveSideIdea">{{ __("Add") }}</Button>
				</div>
			</template>
		</Dialog>
	</div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue"
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from "vue-router"
import { Badge, call } from "frappe-ui"
import DocSyncBanner from "@spa/components/DocSyncBanner.vue"
import RichTextField from "@spa/components/RichTextField.vue"
import StageIcon from "@spa/components/StageIcon.vue"
import StageSteps from "@spa/components/StageSteps.vue"
import { useAutosaveDoc } from "@spa/composables/useAutosaveDoc.js"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { formatDatetime } from "@spa/utils/datetime.js"
import { deskRecordUrl } from "@spa/utils/deskUrl.js"
import { __ } from "@spa/utils/i18n.js"
import { notify } from "@spa/utils/notify.js"
import spaConfig from "../config"
import { ageLabel, applyIdea, loadIdeaOptions, loadIdeas, stageJob, stageSteps } from "../ideasStore.js"

const props = defineProps({ name: { type: String, required: true } })
const API = spaConfig.api
const route = useRoute()
const router = useRouter()

const idea = ref(null)
const error = ref("")
const titleInput = ref(null)
const steps = computed(() => stageSteps())
const composted = computed(() => autosave.draft.stage === "Compost")
const closed = computed(() => ["Harvest", "Compost"].includes(autosave.draft.stage))

function adopt(doc) {
	idea.value = doc
	applyIdea(doc)
}

const autosave = useAutosaveDoc({
	doc: () => idea.value,
	fields: {
		title: { kind: "text", trim: true, required: true, label: __("Title") },
		content: { kind: "html", label: __("Content") },
		stage: { kind: "select", immediate: true, label: __("Stage") },
	},
	request: (name, payload, modified) => ({ method: `${API}.update_idea`, args: { name, ...payload, modified } }),
	fetch: (name) => call(`${API}.get_idea`, { name }),
	onSaved: adopt,
	onRemoteApplied: adopt,
	onError: (message) => notify.error(message),
})

async function load(name) {
	error.value = ""
	try {
		idea.value = await call(`${API}.get_idea`, { name })
	} catch (e) {
		idea.value = null
		error.value = e?.messages?.[0] || e?.message || __("Could not open this idea")
	}
}

// Leaving the editor closes the edit as one version in the idea's history. Blur and route leave
// often come together; they share one request.
let snapshotting = null
function snapshot(name = idea.value?.name) {
	if (!name) return Promise.resolve()
	if (!snapshotting) {
		snapshotting = autosave
			.flush()
			.then(() => call(`${API}.snapshot_idea`, { name }))
			.catch(() => {})
			.finally(() => (snapshotting = null))
	}
	return snapshotting
}

async function onTitleBlur() {
	await autosave.setFocused("title", false)
}

async function onContentBlur() {
	await autosave.setFocused("content", false)
	snapshot()
}

async function startWriting() {
	await snapshot()
	router.push({ name: "IdeaWrite", params: { name: idea.value.name } })
}

function setStage(stage) {
	autosave.draft.stage = stage
}

function compost() {
	if (!window.confirm(__("Compost this idea? It leaves your list but keeps its history; you can take it up again."))) return
	setStage("Compost")
}

// Side ideas from the page (the writing mode captures them too).
const sideOpen = ref(false)
const sideText = ref("")
const sideSaving = ref(false)
const sideInput = ref(null)

function openSideIdea() {
	sideText.value = ""
	sideOpen.value = true
	nextTick(() => sideInput.value?.focus())
}

async function saveSideIdea() {
	sideSaving.value = true
	try {
		await call(`${API}.capture_side_idea`, { parent: idea.value.name, text: sideText.value })
		sideOpen.value = false
		await load(idea.value.name)
		notify.success(__("Idea captured"))
	} catch (e) {
		notify.error(__("Could not add the idea"), e?.messages?.[0] || e?.message || "")
	} finally {
		sideSaving.value = false
	}
}

useUserRealtime(
	"cockpit_idea_changed",
	(payload) => {
		if (payload?.name === idea.value?.name) autosave.noteRemoteModified(payload.modified)
		else loadIdeas()
	},
	{ debounceMs: 300 }
)

onBeforeRouteUpdate(async (to) => {
	await snapshot()
	await load(to.params.name)
})
onBeforeRouteLeave(() => {
	snapshot()
})

onMounted(async () => {
	loadIdeaOptions()
	await load(props.name)
	if (route.query.fresh) nextTick(() => titleInput.value?.select())
})

defineExpose({ idea, autosave, flush: () => autosave.flush() })
</script>
