<template>
	<!--
		The space creator (#2060, #2072): a meeting space (name, Jitsi URL, chat) or the start space,
		where chips are beamed in when people come in.
	-->
	<Dialog v-model="open" :options="{ title: area?.name ? __('Edit space') : __('New space'), size: 'md' }">
		<template #body-content>
			<form class="space-y-3" @submit.prevent="save">
				<div class="grid grid-cols-2 gap-1 rounded-lg bg-surface-gray-2 p-1" role="radiogroup" :aria-label="__('Kind of space')">
					<button
						v-for="option in KINDS"
						:key="option.kind"
						type="button"
						role="radio"
						:aria-checked="kind === option.kind"
						class="flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-sm"
						:class="kind === option.kind ? 'bg-surface-white font-medium text-ink-gray-9 shadow-sm' : 'text-ink-gray-6 hover:text-ink-gray-8'"
						:data-testid="`area-kind-${option.kind}`"
						@click="kind = option.kind"
					>
						<FeatherIcon :name="option.icon" class="h-4 w-4" />
						{{ option.label }}
					</button>
				</div>
				<FormControl
					v-model="title"
					:label="__('Name')"
					:placeholder="kind === 'Start' ? __('Entrance') : __('Standup')"
					:maxlength="60"
					autofocus
				/>
				<p v-if="KIND_HINTS[kind]" class="text-xs text-ink-gray-5" data-testid="area-kind-hint">
					{{ KIND_HINTS[kind] }}
				</p>
				<!-- A cockpit space (#2076): which cockpit opens here. -->
				<FormControl
					v-if="kind === 'Cockpit'"
					v-model="cockpit"
					type="select"
					:label="__('Cockpit')"
					:options="[{ label: __('Pick a cockpit'), value: '' }, ...cockpitOptions]"
					data-testid="area-cockpit-select"
				/>
				<!-- Every kind but Start has a meeting (optional for a cockpit space). -->
				<template v-if="kind !== 'Start'">
				<FormControl
					v-model="url"
					:label="kind === 'Cockpit' ? __('Jitsi meeting URL (optional)') : __('Jitsi meeting URL')"
					placeholder="https://meet.jit.si/FullTimeDefencesRejectOverly"
				/>
				<p class="text-xs text-ink-gray-5">
					{{ __("Whoever stops inside the area joins this meeting, with microphone and camera off.") }}
				</p>
				<p v-if="kind === 'Guest' || kind === 'Customer meeting'" class="text-xs text-ink-gray-5">
					{{ __("Chat: the guest chat, kept only for a short while (comes with the guest chat).") }}
				</p>
				<FormControl
					v-if="kind === 'Meeting' || (kind === 'Cockpit' && url)"
					v-model="chatMode"
					type="select"
					:label="__('Chat')"
					:options="[
						{ label: __('Saved: history is kept, can be burned'), value: 'Saved' },
						{ label: __('Not saved: deleted when the last person leaves'), value: 'Not saved' },
						{ label: __('Confidential: never stored, only live'), value: 'Confidential' },
					]"
					data-testid="area-chat-mode-select"
				/>
				</template>
				<p v-if="error" class="text-sm text-ink-red-4">{{ error }}</p>
				<button type="submit" class="hidden" />
			</form>
		</template>
		<template #actions>
			<div class="flex items-center gap-2">
				<Button v-if="area?.name" variant="subtle" theme="red" :loading="busy === 'delete'" @click="remove">
					{{ __("Delete") }}
				</Button>
				<Button class="ml-auto" variant="ghost" @click="open = false">{{ __("Cancel") }}</Button>
				<Button variant="solid" :loading="busy === 'save'" @click="save">{{ __("Save") }}</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { Button, call, Dialog, FeatherIcon, FormControl } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	/** { name?, title?, meeting_url?, x, y, width, height } or null (closed) */
	area: { type: Object, default: null },
	/** async (values) => void; throws with a readable message */
	onSave: { type: Function, required: true },
	onDelete: { type: Function, required: true },
})
const emit = defineEmits(["close"])

const open = computed({
	get: () => Boolean(props.area),
	set: (value) => !value && emit("close"),
})
const KINDS = [
	{ kind: "Meeting", icon: "video", label: __("Meeting") },
	{ kind: "Start", icon: "log-in", label: __("Start") },
	{ kind: "Guest", icon: "user-plus", label: __("Guest area") },
	{ kind: "Customer meeting", icon: "briefcase", label: __("Customer meeting") },
	{ kind: "Cockpit", icon: "grid", label: __("Cockpit space") },
]
// What each kind does (#2072, #2081).
const KIND_HINTS = {
	Start: __("People coming in are beamed in here: on their first visit of the day, or when they are back after more than 5 minutes. There is only one start space."),
	Guest: __("External guests arrive here through the guest link and can only move inside it. Employees walk in and out freely and meet them in its meeting. There is only one guest area."),
	"Customer meeting": __("A meeting room for guests: employees invite a guest from the guest area to come here."),
	Cockpit: __("Stopping inside opens this cockpit, for everyone who may open it (each person can switch that off). A meeting is optional."),
}
const kind = ref("Meeting")
const cockpit = ref("")
const cockpitOptions = ref([])
async function loadCockpits() {
	if (cockpitOptions.value.length) return
	try {
		const rows = await call("phamos.api.ophice.cockpit_choices")
		cockpitOptions.value = (rows || []).map((c) => ({ label: c.title, value: c.route }))
	} catch {
		cockpitOptions.value = []
	}
}
watch(kind, (value) => value === "Cockpit" && loadCockpits(), { immediate: true })
const title = ref("")
const url = ref("")
const chatMode = ref("Saved")
const error = ref("")
const busy = ref("")

watch(
	() => props.area,
	(area) => {
		kind.value = area?.kind || "Meeting"
		cockpit.value = area?.cockpit || ""
		title.value = area?.title || ""
		url.value = area?.meeting_url || ""
		chatMode.value = area?.chat_mode || "Saved"
		error.value = ""
	},
	{ immediate: true }
)

async function save() {
	busy.value = "save"
	error.value = ""
	try {
		await props.onSave({
			...props.area,
			kind: kind.value,
			title: title.value,
			meeting_url: kind.value === "Start" ? "" : url.value,
			chat_mode: chatMode.value,
			cockpit: kind.value === "Cockpit" ? cockpit.value : "",
		})
		emit("close")
	} catch (e) {
		error.value = e?.message || __("The area could not be saved.")
	} finally {
		busy.value = ""
	}
}

async function remove() {
	busy.value = "delete"
	try {
		await props.onDelete(props.area)
		emit("close")
	} catch (e) {
		error.value = e?.message || __("The area could not be deleted.")
	} finally {
		busy.value = ""
	}
}
</script>
