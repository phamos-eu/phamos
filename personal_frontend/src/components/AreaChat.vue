<template>
	<!--
		The chat of the meeting area I stand in (#2062, #2066), above the mini map. It comes in
		batches, one per meeting. The running one waits a grace time after the room empties; then the
		area's mode decides (Saved keeps it, Not saved deletes it unless someone saved it). Save and
		Burn are a vote among the people who were there; a tie keeps the chat. Confidential stores nothing.
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
			<button
				v-if="mode !== 'Confidential' && batches.length"
				type="button"
				class="flex-shrink-0 rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-red-4"
				:class="{ 'bg-surface-gray-2 text-ink-red-4': picking }"
				:title="__('Burn chats: pick which meetings to delete')"
				data-testid="area-chat-burn"
				@click="togglePicker"
			>
				<FeatherIcon name="trash-2" class="h-4 w-4" />
			</button>
		</header>

		<!-- Which meetings' chats to burn: each ticked one goes to a vote among its participants. -->
		<div
			v-if="picking"
			class="flex max-h-56 flex-shrink-0 flex-col border-b border-outline-gray-2 bg-surface-gray-1 text-xs"
			data-testid="area-chat-picker"
		>
			<p class="px-3 pt-2 text-ink-gray-6">
				{{ __("Tick the meetings whose chat should be burned. The people who were there vote; a tie keeps it.") }}
			</p>
			<div class="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 py-1.5">
				<label
					v-for="batch in [...batches].reverse()"
					:key="batch.name"
					class="flex items-center gap-2 rounded px-1.5 py-1"
					:class="batch.mine ? 'cursor-pointer hover:bg-surface-gray-2' : 'cursor-not-allowed opacity-50'"
					:title="batch.mine ? '' : __('Only the people who were in this meeting can burn its chat.')"
				>
					<input
						v-model="picked"
						type="checkbox"
						class="form-checkbox"
						:value="batch.name"
						:disabled="!batch.mine"
					/>
					<span class="min-w-0 flex-1 truncate text-ink-gray-8">
						{{ when(batch) }} · {{ who(batch) }}
					</span>
					<span class="flex-shrink-0 text-ink-gray-5">{{ __("{0} msg.", [batch.messages.length]) }}</span>
				</label>
			</div>
			<div class="flex items-center justify-end gap-2 border-t border-outline-gray-2 px-3 py-1.5">
				<Button size="sm" variant="ghost" @click="togglePicker">{{ __("Cancel") }}</Button>
				<Button
					size="sm"
					variant="solid"
					theme="red"
					:disabled="!picked.length"
					:loading="busy === 'pick'"
					data-testid="area-chat-burn-confirm"
					@click="burnPicked"
				>
					{{ picked.length ? __("Vote to burn {0}", [picked.length]) : __("Vote to burn") }}
				</Button>
			</div>
		</div>

		<p class="flex-shrink-0 border-b border-outline-gray-1 bg-surface-gray-1 px-3 py-1 text-xs text-ink-gray-5">
			{{ MODES[mode].hint }}
		</p>

		<div ref="list" class="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-2" data-testid="area-chat-messages">
			<p v-if="loading && !batches.length && !live.length" class="text-xs text-ink-gray-5">{{ __("Loading…") }}</p>
			<p v-else-if="error" class="text-xs text-ink-red-4">{{ error }}</p>
			<p v-else-if="!batches.length && !live.length" class="text-xs text-ink-gray-5">
				{{ __("No messages yet. Say hello to the room.") }}
			</p>

			<template v-for="batch in batches" :key="batch.name">
				<!-- One meeting: when, who, and what happens to its chat. -->
				<div class="sticky top-0 z-10 -mx-3 bg-surface-white/95 px-3 py-1 backdrop-blur" data-testid="area-chat-batch">
					<div class="flex items-center gap-2 text-[11px] text-ink-gray-5">
						<span class="h-px flex-1 bg-outline-gray-2" />
						<span class="truncate">{{ when(batch) }} · {{ who(batch) }}</span>
						<span class="h-px flex-1 bg-outline-gray-2" />
					</div>
					<div
						v-if="stateOf(batch)"
						class="mt-1 flex flex-wrap items-center gap-1.5 rounded-lg px-2 py-1 text-xs"
						:class="stateOf(batch).tone"
					>
						<FeatherIcon :name="stateOf(batch).icon" class="h-3 w-3 flex-shrink-0" />
						<span class="min-w-0 flex-1">{{ stateOf(batch).text }}</span>
						<template v-if="batch.mine">
							<Button
								v-if="canSave(batch)"
								size="sm"
								variant="solid"
								:loading="busy === `${batch.name}:Keep`"
								data-testid="area-chat-save"
								@click="vote(batch, 'Keep')"
							>
								{{ batch.vote_until ? __("Keep") : __("Save") }}
							</Button>
							<Button
								v-if="batch.vote_until && !batch.my_vote"
								size="sm"
								variant="subtle"
								theme="red"
								:loading="busy === `${batch.name}:Burn`"
								@click="vote(batch, 'Burn')"
							>
								{{ __("Burn") }}
							</Button>
						</template>
					</div>
				</div>
				<div
					v-for="message in batch.messages"
					:key="message.name"
					class="flex flex-col"
					:class="message.owner === me ? 'items-end' : 'items-start'"
				>
					<span v-if="message.owner !== me" class="text-[11px] text-ink-gray-5">{{ nameIn(batch, message.owner) }}</span>
					<span
						class="max-w-[90%] whitespace-pre-wrap break-words rounded-lg px-2.5 py-1.5 text-sm"
						:class="message.owner === me ? 'bg-surface-gray-7 text-ink-white' : 'bg-surface-gray-2'"
					>{{ message.text }}</span>
				</div>
			</template>

			<!-- Confidential: only what came in while this page is open. -->
			<div
				v-for="message in live"
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
import { clockTime, relativeTime } from "../utils/ophiceTime.js"

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
		hint: __("Each meeting's chat is kept. The people who were there can vote to burn it."),
	},
	"Not saved": {
		label: __("Not saved"),
		icon: "clock",
		badge: "bg-surface-amber-2 text-ink-amber-3",
		hint: __("Each meeting's chat is deleted 10 minutes after the room empties, unless someone saves it."),
	},
	Confidential: {
		label: __("Confidential"),
		icon: "lock",
		badge: "bg-surface-gray-7 text-ink-white",
		hint: __("Never stored. Only people in the room see it, only now."),
	},
}

const mode = ref(MODES[props.area.chat_mode] ? props.area.chat_mode : "Saved")
const batches = ref([])
const live = ref([])
const loading = ref(true)
const error = ref("")
const text = ref("")
const sending = ref(false)
const picking = ref(false)
const picked = ref([])
const busy = ref("")
const list = ref(null)
const input = ref(null)
// Server times come as "seconds from now": anchored to this browser's clock on load.
const loadedAt = ref(Date.now())
const now = ref(Date.now())
const ticker = setInterval(() => (now.value = Date.now()), 15000)

function scrollDown() {
	nextTick(() => list.value && (list.value.scrollTop = list.value.scrollHeight))
}

function errorText(e) {
	return e?.messages?.[0] || e?.message || ""
}

function at(seconds) {
	return seconds == null ? null : new Date(loadedAt.value + seconds * 1000)
}

function when(batch) {
	const start = at(batch.started_in)
	return start ? clockTime(start, new Date(now.value)) : ""
}

function who(batch) {
	return batch.participants.map((user) => (user === props.me ? __("you") : firstName(batch, user))).join(", ")
}

function firstName(batch, user) {
	return (nameIn(batch, user) || "").split(" ")[0]
}

function nameIn(batch, user) {
	return batch.names?.[user] || props.nameOf(user)
}

function stateOf(batch) {
	const current = new Date(now.value)
	if (batch.vote_until) {
		const ends = at(batch.vote_in)
		return {
			icon: "users",
			tone: "bg-surface-amber-1 text-ink-amber-3",
			text: batch.my_vote
				? __("Vote: {0} keep, {1} burn. You voted {2}. Decided {3} at the latest; a tie keeps it.", [
						batch.keep_votes,
						batch.burn_votes,
						batch.my_vote === "Keep" ? __("keep") : __("burn"),
						relativeTime(ends, current),
				  ])
				: __("Vote: {0} keep, {1} burn. Keep or burn this chat? Decided {2} at the latest; a tie keeps it.", [
						batch.keep_votes,
						batch.burn_votes,
						relativeTime(ends, current),
				  ]),
		}
	}
	if (batch.status === "Ending") {
		const ends = at(batch.grace_in)
		const kept = mode.value === "Saved" || batch.saved
		return {
			icon: kept ? "archive" : "clock",
			tone: kept ? "bg-surface-gray-2 text-ink-gray-7" : "bg-surface-red-1 text-ink-red-4",
			text: kept
				? __("The room is empty. This chat will be kept {0}.", [relativeTime(ends, current)])
				: __("The room is empty. This chat is deleted {0} unless someone saves it.", [relativeTime(ends, current)]),
		}
	}
	if (batch.status === "Open" && mode.value === "Not saved") {
		return batch.saved
			? { icon: "check", tone: "bg-surface-green-1 text-ink-green-3", text: __("This meeting's chat is saved.") }
			: {
					icon: "clock",
					tone: "bg-surface-gray-2 text-ink-gray-7",
					text: __("This meeting's chat is temporary until someone saves it."),
			  }
	}
	return null
}

function canSave(batch) {
	if (batch.vote_until) return !batch.my_vote
	return mode.value === "Not saved" && !batch.saved && batch.status !== "Kept"
}

async function load() {
	loading.value = true
	error.value = ""
	try {
		const data = await call(`${API}.get_area_chat`, { area: props.area.name })
		loadedAt.value = Date.now()
		now.value = loadedAt.value
		mode.value = MODES[data.mode] ? data.mode : "Saved"
		batches.value = data.batches || []
		if (mode.value !== "Confidential") live.value = []
		picked.value = picked.value.filter((name) => batches.value.some((b) => b.name === name && b.mine))
		scrollDown()
	} catch (e) {
		error.value = errorText(e) || __("The chat could not be loaded.")
	} finally {
		loading.value = false
	}
}

function add(message, batchName) {
	if (!message?.name) return
	if (!batchName) {
		if (!live.value.some((m) => m.name === message.name)) live.value.push(message)
		scrollDown()
		return
	}
	const batch = batches.value.find((b) => b.name === batchName)
	// A batch this page doesn't know yet (the meeting just started): fetch it whole.
	if (!batch) return load()
	if (!batch.messages.some((m) => m.name === message.name)) batch.messages.push(message)
	scrollDown()
}

async function send() {
	const value = text.value.trim()
	if (!value || sending.value) return
	sending.value = true
	try {
		const row = await call(`${API}.send_area_message`, { area: props.area.name, text: value })
		add(row, row.batch)
		text.value = ""
	} catch (e) {
		error.value = errorText(e) || __("The message could not be sent.")
	} finally {
		sending.value = false
		// Keeps the keyboard for the next message.
		nextTick(() => input.value?.focus())
	}
}

async function vote(batch, choice) {
	busy.value = `${batch.name}:${choice}`
	try {
		await call(`${API}.vote_batch`, { batch: batch.name, vote: choice })
		await load()
	} catch (e) {
		error.value = errorText(e) || __("Your vote could not be saved.")
	} finally {
		busy.value = ""
	}
}

function togglePicker() {
	picking.value = !picking.value
	picked.value = []
}

async function burnPicked() {
	busy.value = "pick"
	try {
		for (const name of picked.value) await call(`${API}.vote_batch`, { batch: name, vote: "Burn" })
		picking.value = false
		picked.value = []
		await load()
	} catch (e) {
		error.value = errorText(e) || __("Your vote could not be saved.")
	} finally {
		busy.value = ""
	}
}

function onMessage(payload) {
	if (payload?.area === props.area.name) add(payload.message, payload.batch)
}

// Batches change (someone joined, voted, the grace time ran out): reload, at most every second.
let reloadTimer = null
function onBatches(payload) {
	if (payload?.area !== props.area.name) return
	clearTimeout(reloadTimer)
	reloadTimer = setTimeout(load, 300)
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
	props.socket?.on?.("ophice_area_batches", onBatches)
})
onBeforeUnmount(() => {
	clearInterval(ticker)
	clearTimeout(reloadTimer)
	props.socket?.off?.("ophice_area_message", onMessage)
	props.socket?.off?.("ophice_area_batches", onBatches)
})
</script>
