<template>
	<!-- Chat with someone (#2063): our direct message, or the channels we share. Opens Raven. -->
	<div
		ref="root"
		class="fixed z-50 w-72 rounded-xl border border-outline-gray-2 bg-surface-white p-2 text-sm text-ink-gray-9 shadow-2xl"
		:style="position"
		role="dialog"
		:aria-label="__('Chat with {0}', [person.full_name])"
		data-testid="chat-with"
		tabindex="-1"
		@keydown.esc.stop.prevent="$emit('close')"
	>
		<div class="flex items-center gap-2 px-1.5 pb-2">
			<UserAvatar :name="person.user" :label="person.full_name" :image="person.user_image" size="sm" />
			<span class="min-w-0 flex-1 truncate font-medium">{{ person.full_name }}</span>
			<button type="button" class="rounded p-0.5 text-ink-gray-5 hover:bg-surface-gray-2" :title="__('Close')" @click="$emit('close')">
				<FeatherIcon name="x" class="h-4 w-4" />
			</button>
		</div>
		<!-- Find people (PM, 2026-11-22): go to them, or call them to a meeting point. -->
		<div v-if="onMap" class="flex items-center gap-1.5 px-1.5 pb-2" data-testid="chat-with-actions">
			<GoToButton @go="(mode) => $emit('go', mode)" />
			<!-- Guests get no meeting point: they have their own invite (#2084). -->
			<Button v-if="!person.guest" size="sm" variant="subtle" :title="__('Set a meeting point for the two of you')" class="whitespace-nowrap" data-testid="meeting-point" @click="$emit('pin')">
				<template #prefix><FeatherIcon name="map-pin" class="h-3.5 w-3.5" /></template>
				{{ __("Meeting point") }}
			</Button>
		</div>
		<div v-if="person.working_on" class="px-1.5 pb-2">
			<p class="pb-1 text-xs font-medium text-ink-gray-5">{{ __("Working on") }}</p>
			<WorkingOnCard :card="person.working_on" />
		</div>
		<p v-if="loading" class="px-1.5 py-1 text-xs text-ink-gray-5">{{ __("Loading…") }}</p>
		<p v-else-if="error" class="px-1.5 py-1 text-xs text-ink-red-4">{{ error }}</p>
		<template v-else>
			<button
				type="button"
				class="flex w-full items-center gap-2 rounded-lg px-1.5 py-1.5 text-left hover:bg-surface-gray-2"
				data-testid="chat-with-dm"
				@click="openDm"
			>
				<FeatherIcon name="message-circle" class="h-4 w-4 flex-shrink-0 text-ink-gray-6" />
				<span class="min-w-0 flex-1 truncate">{{ options?.dm ? __("Direct message") : __("New direct message") }}</span>
				<span v-if="options?.dm?.last_message_at" class="flex-shrink-0 text-xs text-ink-gray-5">{{ ago(options.dm.last_message_at) }}</span>
			</button>
			<template v-if="options?.chats?.length">
				<p class="px-1.5 pb-0.5 pt-2 text-xs font-medium text-ink-gray-5">{{ __("Recent chats together") }}</p>
				<a
					v-for="chat in options.chats"
					:key="chat.url"
					:href="chat.url"
					target="_blank"
					rel="noopener"
					class="flex items-center gap-2 rounded-lg px-1.5 py-1.5 hover:bg-surface-gray-2"
					data-testid="chat-with-channel"
					@click="$emit('close')"
				>
					<FeatherIcon :name="chat.type === 'Private' ? 'lock' : 'hash'" class="h-4 w-4 flex-shrink-0 text-ink-gray-6" />
					<span class="min-w-0 flex-1 truncate">{{ chat.label }}</span>
					<span v-if="chat.last_message_at" class="flex-shrink-0 text-xs text-ink-gray-5">{{ ago(chat.last_message_at) }}</span>
				</a>
			</template>
		</template>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { Button, call, FeatherIcon } from "frappe-ui"
import GoToButton from "./GoToButton.vue"
import UserAvatar from "@spa/components/UserAvatar.vue"
import WorkingOnCard from "./WorkingOnCard.vue"
import { __ } from "@spa/utils/i18n.js"
import { relativeTime } from "../utils/ophiceTime.js"

const props = defineProps({
	/** { user, full_name, user_image } */
	person: { type: Object, required: true },
	/** where it was asked for: { x, y } in px of the window */
	at: { type: Object, required: true },
	/** Their chip is on the map: Go to and Meeting point. */
	onMap: { type: Boolean, default: false },
})
const emit = defineEmits(["close", "go", "pin"])

const API = "phamos.api.ophice"
const root = ref(null)
const options = ref(null)
const loading = ref(true)
const error = ref("")

// Next to the click, kept inside the window.
const position = computed(() => ({
	left: `${Math.max(8, Math.min(window.innerWidth - 296, props.at.x + 8))}px`,
	top: `${Math.max(8, Math.min(window.innerHeight - 260, props.at.y + 8))}px`,
}))

function errorText(e) {
	const first = Array.isArray(e?.messages) ? e.messages[0] : e?.message
	return typeof first === "string" ? new DOMParser().parseFromString(first, "text/html").body.textContent : ""
}

// "2 days ago" from last_message_at: an ISO instant with its offset (phamos.api.ophice._as_instant).
function ago(value) {
	const date = new Date(String(value))
	return Number.isNaN(date.getTime()) ? "" : relativeTime(date)
}

async function openDm() {
	try {
		const url = options.value?.dm?.url || (await call(`${API}.start_direct_message`, { user: props.person.user })).url
		window.open(url, "_blank", "noopener")
		emit("close")
	} catch (e) {
		error.value = errorText(e) || __("The chat could not be opened.")
	}
}

function onPointerDown(event) {
	if (root.value && !root.value.contains(event.target)) emit("close")
}

onMounted(async () => {
	root.value?.focus()
	// After this click: the click that opened the menu must not close it again.
	setTimeout(() => window.addEventListener("pointerdown", onPointerDown, true))
	try {
		options.value = await call(`${API}.get_chat_options`, { user: props.person.user })
	} catch (e) {
		error.value = errorText(e) || __("The chats could not be loaded.")
	} finally {
		loading.value = false
	}
})
onBeforeUnmount(() => window.removeEventListener("pointerdown", onPointerDown, true))
</script>
