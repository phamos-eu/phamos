<template>
	<!--
		The chat of the meeting area I stand in (#2062), above the mini map. Its mode is the area's:
		Saved (history kept, can be burned), Not saved (gone when the last person leaves),
		Confidential (never stored, only live).
	-->
	<section
		class="flex min-h-0 flex-col overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-white text-ink-gray-9 shadow-xl"
		:aria-label="__('Chat of {0}', [area.title])"
		data-testid="area-chat"
	>
		<header class="flex flex-shrink-0 items-center gap-2 border-b border-outline-gray-2 px-3 py-2">
			<FeatherIcon name="message-square" class="h-4 w-4 flex-shrink-0 text-ink-gray-6" />
			<span class="min-w-0 flex-1 truncate text-sm font-medium">{{ area.title }}</span>
			<span
				class="inline-flex flex-shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs"
				:class="MODES[mode].badge"
				:title="MODES[mode].hint"
				data-testid="area-chat-mode"
			>
				<FeatherIcon :name="MODES[mode].icon" class="h-3 w-3" />
				{{ MODES[mode].label }}
			</span>
			<template v-if="mode !== 'Confidential'">
				<button
					type="button"
					class="flex-shrink-0 rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-red-4"
					:title="__('Burn chat now: deletes the history for everyone')"
					data-testid="area-chat-burn"
					@click="confirmBurn = true"
				>
					<FeatherIcon name="trash-2" class="h-4 w-4" />
				</button>
			</template>
		</header>
		<div
			v-if="confirmBurn"
			class="flex flex-shrink-0 flex-wrap items-center gap-2 border-b border-outline-gray-2 bg-surface-red-1 px-3 py-2 text-xs text-ink-red-4"
		>
			<span class="min-w-0 flex-1">{{ __("Delete this room's history for everyone? This cannot be undone.") }}</span>
			<Button size="sm" variant="solid" theme="red" :loading="burning" data-testid="area-chat-burn-confirm" @click="burn">
				{{ __("Burn") }}
			</Button>
			<Button size="sm" variant="ghost" @click="confirmBurn = false">{{ __("Cancel") }}</Button>
		</div>
		<p class="flex-shrink-0 border-b border-outline-gray-1 bg-surface-gray-1 px-3 py-1 text-xs text-ink-gray-5">
			{{ MODES[mode].hint }}
		</p>
		<div ref="list" class="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-2" data-testid="area-chat-messages">
			<p v-if="loading" class="text-xs text-ink-gray-5">{{ __("Loading…") }}</p>
			<p v-else-if="error" class="text-xs text-ink-red-4">{{ error }}</p>
			<p v-else-if="!messages.length" class="text-xs text-ink-gray-5">{{ __("No messages yet. Say hello to the room.") }}</p>
			<div
				v-for="message in messages"
				:key="message.name"
				class="flex flex-col"
				:class="message.owner === me ? 'items-end' : 'items-start'"
			>
				<span v-if="message.owner !== me" class="text-[11px] text-ink-gray-5">{{ nameOf(message.owner) }}</span>
				<span
					class="max-w-[90%] whitespace-pre-wrap break-words rounded-lg px-2.5 py-1.5 text-sm"
					:class="message.owner === me ? 'bg-surface-gray-7 text-ink-white' : 'bg-surface-gray-2'"
				>{{ message.text }}</span>
			</div>
		</div>
		<form class="flex flex-shrink-0 items-end gap-2 border-t border-outline-gray-2 p-2" @submit.prevent="send">
			<textarea
				ref="input"
				v-model="text"
				rows="1"
				maxlength="2000"
				class="form-textarea min-h-[34px] flex-1 resize-none rounded border-outline-gray-2 bg-surface-gray-2 text-sm text-ink-gray-9"
				:placeholder="__('Message the room')"
				:title="__('Enter sends, Esc goes back to the map')"
				data-testid="area-chat-input"
				@keydown.enter.exact.prevent="send"
				@keydown.esc.stop.prevent="$event.target.blur()"
			/>
			<Button type="submit" variant="solid" :loading="sending" :disabled="!text.trim()">
				<FeatherIcon name="send" class="h-4 w-4" />
			</Button>
		</form>
	</section>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { Button, call, FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	/** { name, title, chat_mode } */
	area: { type: Object, required: true },
	/** my user id */
	me: { type: String, required: true },
	/** user id → full name */
	nameOf: { type: Function, default: (user) => user },
	/** the cockpit socket (or null) */
	socket: { type: Object, default: null },
})

const API = "phamos.api.ophice"
const MODES = {
	Saved: {
		label: __("Saved"),
		icon: "archive",
		badge: "bg-surface-green-2 text-ink-green-3",
		hint: __("History is kept for this room. Anyone in the room can burn it."),
	},
	"Not saved": {
		label: __("Not saved"),
		icon: "clock",
		badge: "bg-surface-amber-2 text-ink-amber-3",
		hint: __("Deleted for good when the last person leaves the room."),
	},
	Confidential: {
		label: __("Confidential"),
		icon: "lock",
		badge: "bg-surface-gray-7 text-ink-white",
		hint: __("Never stored. Only people in the room see it, only now."),
	},
}

const mode = ref(MODES[props.area.chat_mode] ? props.area.chat_mode : "Saved")
const messages = ref([])
const loading = ref(true)
const error = ref("")
const text = ref("")
const sending = ref(false)
const confirmBurn = ref(false)
const burning = ref(false)
const list = ref(null)
const input = ref(null)

function scrollDown() {
	nextTick(() => list.value && (list.value.scrollTop = list.value.scrollHeight))
}

function errorText(e) {
	return e?.messages?.[0] || e?.message || ""
}

async function load() {
	loading.value = true
	error.value = ""
	try {
		const data = await call(`${API}.get_area_chat`, { area: props.area.name })
		mode.value = MODES[data.mode] ? data.mode : "Saved"
		messages.value = data.messages || []
		scrollDown()
	} catch (e) {
		error.value = errorText(e) || __("The chat could not be loaded.")
	} finally {
		loading.value = false
	}
}

function add(message) {
	if (!message?.name || messages.value.some((m) => m.name === message.name)) return
	messages.value.push(message)
	scrollDown()
}

async function send() {
	const value = text.value.trim()
	if (!value || sending.value) return
	sending.value = true
	try {
		add(await call(`${API}.send_area_message`, { area: props.area.name, text: value }))
		text.value = ""
	} catch (e) {
		error.value = errorText(e) || __("The message could not be sent.")
	} finally {
		sending.value = false
		// Keeps the keyboard for the next message.
		nextTick(() => input.value?.focus())
	}
}

async function burn() {
	burning.value = true
	try {
		await call(`${API}.burn_area_chat`, { area: props.area.name })
		messages.value = []
		confirmBurn.value = false
	} catch (e) {
		error.value = errorText(e) || __("The chat could not be burned.")
	} finally {
		burning.value = false
	}
}

function onMessage(payload) {
	if (payload?.area === props.area.name) add(payload.message)
}
function onBurned(payload) {
	if (payload?.area === props.area.name) messages.value = []
}

watch(
	() => props.area.chat_mode,
	(value) => {
		if (value && value !== mode.value) load()
	}
)
watch(() => props.area.name, load)

onMounted(() => {
	load()
	props.socket?.on?.("ophice_area_message", onMessage)
	props.socket?.on?.("ophice_area_burned", onBurned)
})
onBeforeUnmount(() => {
	props.socket?.off?.("ophice_area_message", onMessage)
	props.socket?.off?.("ophice_area_burned", onBurned)
})
</script>
