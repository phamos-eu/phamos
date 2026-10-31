<template>
	<!-- Writing mode of an idea (#1774). Covers sidebar and header; stays below frappe-ui dialogs
	     (z-10) and toasts. role="dialog" makes the global shortcuts step aside while writing. -->
	<div role="dialog" aria-modal="true" :aria-label="__('Writing')" class="fixed inset-0 z-[5] flex flex-col bg-surface-white">
		<div v-if="error" class="m-auto max-w-md p-6 text-center text-sm text-ink-red-4">
			{{ error }}
			<div class="mt-3"><Button variant="subtle" @click="leave">{{ __("Back to the idea") }}</Button></div>
		</div>
		<div v-else-if="!idea" class="m-auto text-sm text-ink-gray-5">{{ __("Loading the idea…") }}</div>

		<!-- 1. Aim -->
		<div v-else-if="phase === 'aim'" class="m-auto flex w-full max-w-lg flex-col gap-5 p-6 text-center">
			<div>
				<p class="text-xs font-semibold uppercase tracking-wide text-ink-gray-5">{{ __("Writing session") }}</p>
				<h1 class="mt-2 text-2xl font-semibold tracking-tight text-ink-gray-9">{{ idea.title }}</h1>
				<p class="mt-2 text-sm text-ink-gray-5">
					{{ idea.last_session_words ? __("Last time: {0} words", [idea.last_session_words]) : __("First session") }}
				</p>
			</div>
			<div class="flex flex-col gap-2">
				<button
					v-for="option in aimOptions"
					:key="option.value"
					type="button"
					class="flex items-center justify-between rounded-lg border border-outline-gray-2 bg-surface-white px-4 py-3 text-left text-sm text-ink-gray-8 hover:border-outline-gray-4 hover:bg-surface-gray-1"
					@click="start(option.value)"
				>
					<span class="font-medium">{{ option.label }}</span>
					<span class="text-xs text-ink-gray-5">{{ __("Goal: {0} words", [wordGoal(idea.last_session_words, option.value)]) }}</span>
				</button>
			</div>
			<button type="button" class="text-xs text-ink-gray-5 hover:text-ink-gray-8" @click="leave">{{ __("Not now") }}</button>
		</div>

		<!-- 2. Writing and 3. feeling -->
		<template v-else>
			<div class="h-1.5 w-full shrink-0 bg-surface-gray-2">
				<div class="h-full bg-surface-gray-7 transition-[width] duration-500" :style="{ width: `${progressPct}%` }" />
			</div>
			<header class="flex shrink-0 items-center justify-between gap-4 px-5 py-3">
				<h1 class="min-w-0 truncate text-lg font-semibold text-ink-gray-9">{{ idea.title }}</h1>
				<div v-if="phase === 'writing'" class="flex shrink-0 items-center gap-3">
					<span class="text-sm tabular-nums text-ink-gray-6">{{ __("{0} of {1} words", [written, goal]) }}</span>
					<span class="text-xs text-ink-gray-4">{{ saveLabel }}</span>
					<Button variant="solid" @click="openFeeling">{{ __("Complete") }}</Button>
				</div>
			</header>

			<div v-if="phase !== 'writing'" class="mx-auto mb-3 flex w-full max-w-3xl shrink-0 flex-col gap-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4">
				<p class="text-sm font-medium text-ink-gray-9">{{ __("How did it feel?") }}</p>
				<div class="grid grid-cols-3 gap-2">
					<Button
						v-for="feeling in feelings"
						:key="feeling"
						variant="outline"
						:loading="phase === 'saving' && chosen === feeling"
						:disabled="phase === 'saving'"
						@click="finish(feeling)"
					>
						{{ __(feeling) }}
					</Button>
				</div>
				<button type="button" class="self-start text-xs text-ink-gray-5 hover:text-ink-gray-8" :disabled="phase === 'saving'" @click="phase = 'writing'">
					{{ __("Back to writing") }}
				</button>
			</div>

			<div class="flex min-h-0 flex-1 gap-4 px-5 pb-6">
				<div class="mx-auto flex min-h-0 w-full max-w-3xl flex-1">
					<textarea
						ref="writer"
						v-model="autosave.draft.content"
						class="min-h-0 w-full flex-1 resize-none rounded-xl border border-outline-gray-2 bg-surface-white p-5 text-lg leading-relaxed text-ink-gray-9 outline-none focus:border-outline-gray-3 focus:ring-0"
						:placeholder="__('Write. Nothing else is on this screen.')"
						:readonly="phase !== 'writing'"
					/>
				</div>
				<aside class="hidden w-72 shrink-0 flex-col gap-2 border-l border-outline-gray-1 pl-4 md:flex">
					<p class="text-sm font-medium text-ink-gray-8">{{ __("Side idea") }}</p>
					<p class="text-xs text-ink-gray-5">{{ __("Something else came up? Park it here, it becomes its own idea.") }}</p>
					<textarea
						v-model="sideText"
						rows="6"
						class="w-full resize-none rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-2 text-sm text-ink-gray-8 outline-none focus:ring-0"
						:placeholder="__('First line becomes the title…')"
						@input="scheduleCapture"
					/>
					<Button variant="subtle" :disabled="!sideText.trim()" @click="anotherOne">{{ __("Another one") }}</Button>
					<ul v-if="captured.length" class="mt-2 flex flex-wrap gap-1.5">
						<li v-for="item in captured" :key="item.name" class="max-w-full truncate rounded-full bg-surface-gray-2 px-2.5 py-1 text-xs text-ink-gray-7">
							{{ item.title }}
						</li>
					</ul>
				</aside>
			</div>
		</template>
	</div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue"
import { onBeforeRouteLeave, useRouter } from "vue-router"
import { call } from "frappe-ui"
import { useAutosaveDoc } from "@spa/composables/useAutosaveDoc.js"
import { nowForApi } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"
import { countWords, htmlToPlainText, plainTextToHtml, wordGoal } from "@spa/utils/ideaText.js"
import { notify } from "@spa/utils/notify.js"
import spaConfig from "../config"
import { applyIdea } from "../ideasStore.js"

const props = defineProps({ name: { type: String, required: true } })
const API = spaConfig.api
const router = useRouter()

const idea = ref(null)
const error = ref("")
const phase = ref("aim") // aim → writing → feeling → saving
const aim = ref("similar")
const startedOn = ref("")
const wordsAtStart = ref(0)
const chosen = ref("")
let done = false // the session was saved; leaving needs no flush
const writer = ref(null)
const feelings = ["Productive", "Mixed", "Not really"]
const aimOptions = [
	{ value: "more", label: __("More than last time") },
	{ value: "similar", label: __("About the same") },
	{ value: "less", label: __("Less than last time") },
]

const autosave = useAutosaveDoc({
	doc: () => idea.value,
	fields: { content: { kind: "text", toServer: plainTextToHtml, fromServer: htmlToPlainText, label: __("Content") } },
	request: (name, payload, modified) => ({ method: `${API}.update_idea`, args: { name, ...payload, modified } }),
	fetch: (name) => call(`${API}.get_idea`, { name }),
	debounceMs: 2000,
	maxWaitMs: 10000,
	onSaved: applyIdea,
	onError: (message) => notify.error(message),
})

const goal = computed(() => wordGoal(idea.value?.last_session_words, aim.value))
const written = computed(() => Math.max(0, countWords(autosave.draft.content) - wordsAtStart.value))
const progressPct = computed(() => Math.min(100, goal.value ? (written.value / goal.value) * 100 : 0))
const saveLabel = computed(() => ({ saving: __("Saving…"), pending: __("Saving…"), saved: __("Saved"), error: __("Not saved") })[autosave.status] || "")

function start(choice) {
	aim.value = choice
	startedOn.value = nowForApi()
	wordsAtStart.value = countWords(autosave.draft.content)
	phase.value = "writing"
	nextTick(() => {
		const el = writer.value
		if (!el) return
		el.focus()
		el.setSelectionRange(el.value.length, el.value.length)
		el.scrollTop = el.scrollHeight
	})
}

// Side ideas: typing pauses for 1.5 s → a child idea; further typing updates the same child.
const sideText = ref("")
const sideName = ref(null)
const captured = ref([])
let captureTimer = null
let capturing = Promise.resolve()

function scheduleCapture() {
	clearTimeout(captureTimer)
	captureTimer = setTimeout(capture, 1500)
}

function capture() {
	clearTimeout(captureTimer)
	captureTimer = null
	const text = sideText.value.trim()
	if (countWords(text) < 2) return capturing
	capturing = capturing.then(async () => {
		try {
			const doc = await call(`${API}.capture_side_idea`, { parent: props.name, text, name: sideName.value })
			if (!doc) return
			sideName.value = doc.name
			const index = captured.value.findIndex((c) => c.name === doc.name)
			const item = { name: doc.name, title: doc.title }
			if (index >= 0) captured.value.splice(index, 1, item)
			else captured.value.push(item)
		} catch (e) {
			notify.error(__("Could not save the side idea"), e?.messages?.[0] || e?.message || "")
		}
	})
	return capturing
}

async function anotherOne() {
	await capture()
	sideText.value = ""
	sideName.value = null
}

function openFeeling() {
	if (!written.value && !captured.value.length && !sideText.value.trim()) return leave()
	phase.value = "feeling"
}

async function finish(feeling) {
	chosen.value = feeling
	phase.value = "saving"
	try {
		await Promise.all([autosave.flush(), capture()])
		const result = await call(`${API}.complete_idea_writing_session`, {
			name: props.name,
			started_on: startedOn.value,
			words_written: written.value,
			word_goal: goal.value,
			aim_choice: aim.value,
			felt_productive: feeling,
		})
		applyIdea(result.idea)
		notify.success(__("Session saved: {0} words", [written.value]))
		done = true
		router.replace({ name: "IdeaDetail", params: { name: props.name } })
	} catch (e) {
		phase.value = "feeling"
		notify.error(__("Could not save the session"), e?.messages?.[0] || e?.message || "")
	}
}

function leave() {
	router.push({ name: "IdeaDetail", params: { name: props.name } })
}

function onKeydown(event) {
	if (event.key !== "Escape" || event.defaultPrevented) return
	event.preventDefault()
	if (phase.value === "writing") openFeeling()
	else if (phase.value === "feeling") phase.value = "writing"
	else if (phase.value === "aim") leave()
}

onBeforeRouteLeave(async () => {
	if (!done) await Promise.all([autosave.flush(), capture()]).catch(() => {})
})

onMounted(async () => {
	window.addEventListener("keydown", onKeydown)
	try {
		const doc = await call(`${API}.get_idea`, { name: props.name })
		if (["Harvest", "Compost"].includes(doc.stage)) {
			error.value = __("This idea is closed. Take it up again to write on it.")
		}
		idea.value = doc
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not open this idea")
	}
})

onBeforeUnmount(() => {
	window.removeEventListener("keydown", onKeydown)
	clearTimeout(captureTimer)
})
</script>
