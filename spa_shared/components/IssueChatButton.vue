<template>
	<template v-if="state.enabled">
		<!-- Below lg the chat is an overlay this button toggles; from lg on it is a column that is
		     always there, so the button steps aside. -->
		<Button
			v-if="!docked"
			ref="buttonRef"
			:variant="state.is_member ? 'subtle' : 'outline'"
			:loading="busy"
			:title="buttonTitle"
			@click="onClick"
		>
			<template #prefix><FeatherIcon name="message-circle" class="h-3.5 w-3.5" /></template>
			{{ buttonLabel }}
			<template v-if="unreadTotal" #suffix>
				<span
					class="ml-0.5 inline-flex h-4 min-w-[1rem] items-center justify-center gap-0.5 rounded-full bg-surface-red-5 px-1 text-[10px] font-semibold text-ink-white"
					:aria-label="unreadSummary(state)"
				>
					{{ unreadTotal > 99 ? "99+" : unreadTotal }}
					<FeatherIcon v-if="state.unread_threads" name="corner-down-right" class="h-2.5 w-2.5" />
				</span>
			</template>
		</Button>
		<IssueChatPanel
			ref="panelRef"
			v-model:open="drawerOpen"
			:record-name="issueName"
			:url="state.is_member ? state.url || '' : ''"
			:title="`${issueName}: ${subject || ''}`"
			:skipped-users="state.is_member ? state.skipped_users || [] : []"
			@closed="onPanelClosed"
		>
			<template #placeholder>
				<FeatherIcon name="message-circle" class="h-8 w-8 text-ink-gray-4" />
				<template v-if="loading">
					<p class="text-sm text-ink-gray-5">{{ __("Loading the chat…") }}</p>
				</template>
				<template v-else-if="!state.channel_id">
					<p class="text-sm font-medium text-ink-gray-8">{{ __("No chat for this Issue yet.") }}</p>
					<p class="max-w-xs text-xs text-ink-gray-5">
						{{ __("Start one with the people on this Issue. Messages also show up in Raven, linked to the Issue.") }}
					</p>
					<Button variant="solid" :loading="busy" @click="ensure">{{ __("Start chat") }}</Button>
				</template>
				<template v-else>
					<p class="text-sm font-medium text-ink-gray-8">{{ __("You are not in this chat yet.") }}</p>
					<Button variant="solid" :loading="busy" @click="ensure">{{ __("Join chat") }}</Button>
				</template>
			</template>
		</IssueChatPanel>
	</template>
</template>

<script setup>
// The chat of an Issue (#1615). From lg on it is a column of the Issue view that is always there:
// the chat itself, or "Start chat" / "Join chat". Below lg this button shows whether there is a
// chat and how many messages are unread, and opens it as an overlay. "C" toggles the overlay, or
// puts the keyboard into the column. The unread count follows Raven's message_created events in
// the channel's document room.
import { computed, nextTick, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue"
import { Button, call, FeatherIcon, toast } from "frappe-ui"
import IssueChatPanel from "@spa/components/IssueChatPanel.vue"
import { useDocRealtime } from "@spa/composables/useDocRealtime.js"
import { sessionUser } from "@spa/session.js"
import { __ } from "@spa/utils/i18n.js"
import { dialogOpen, insideOverlay, isPlainKey, isTypingTarget } from "@spa/utils/shortcuts.js"
import { chatChanged, issueChatStore } from "@spa/issueChatStore.js"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { totalUnread, unreadSummary } from "@spa/utils/chatUnread.js"

const props = defineProps({
	issueName: { type: String, required: true },
	subject: { type: String, default: "" },
	// Closing or reopening the Issue archives or restores its chat (#1622).
	status: { type: String, default: "" },
	api: { type: String, required: true },
})

const EMPTY = { enabled: false, channel_id: null, url: null, is_member: false, archived: false, unread: 0, unread_threads: 0, skipped_users: [] }
const state = ref({ ...EMPTY })
const busy = ref(false)
const drawerOpen = ref(false)
const buttonRef = ref(null)
const panelRef = ref(null)
const loading = ref(true)
const docked = computed(() => Boolean(panelRef.value?.inColumn))
const unreadTotal = computed(() => totalUnread(state.value))

const buttonLabel = computed(() => {
	if (!state.value.channel_id) return __("Start chat")
	if (!state.value.is_member) return __("Join chat")
	return __("Chat")
})
const buttonTitle = computed(() => {
	if (!state.value.channel_id) return __("Start a Raven chat with the people on this Issue (C)")
	if (!state.value.is_member) return __("Join the Raven chat of this Issue (C)")
	const base = state.value.archived
		? __("Read the chat of this closed Issue (C)")
		: __("Open the Raven chat of this Issue (C)")
	const unread = unreadSummary(state.value)
	return unread ? `${base} · ${unread}` : base
})

function errorText(e) {
	return e?.messages?.[0] || e?.message || __("Something went wrong")
}

async function refresh() {
	const name = props.issueName
	try {
		const result = await call(`${props.api}.get_issue_chat`, { name })
		if (name !== props.issueName) return
		state.value = { ...EMPTY, ...result }
		honourOpenRequest()
	} catch (e) {
		// The chat is an add-on to the Issue; without it the button just stays hidden.
		if (name === props.issueName) state.value = { ...EMPTY }
	} finally {
		if (name === props.issueName) loading.value = false
	}
}

function onPanelClosed() {
	chatChanged()
	refresh()
}

// The chat icon in a list asked for this Issue's chat (issueChatStore.openRequest).
async function honourOpenRequest() {
	// Wait for this Issue's state; refresh() calls again once it is loaded.
	if (issueChatStore.openRequest !== props.issueName || !state.value.channel_id) return
	if (docked.value) {
		issueChatStore.openRequest = null // the column already shows it
		return
	}
	// Only the button on the page takes it, not a kept-alive copy.
	await nextTick()
	const el = buttonRef.value?.$el
	if (!el?.isConnected || el.offsetParent === null) return
	if (issueChatStore.openRequest !== props.issueName) return
	issueChatStore.openRequest = null
	if (!drawerOpen.value) onClick()
}

/** Start or join the chat; true when the user is in it afterwards. */
async function ensure() {
	if (state.value.channel_id && state.value.is_member) return true
	busy.value = true
	try {
		state.value = { ...EMPTY, ...(await call(`${props.api}.ensure_issue_chat`, { name: props.issueName })) }
		chatChanged()
		return true
	} catch (e) {
		toast({ title: errorText(e), icon: "x-circle", iconClasses: "text-ink-red-4" })
		return false
	} finally {
		busy.value = false
	}
}

async function onClick() {
	if (drawerOpen.value) {
		drawerOpen.value = false
		chatChanged()
		return refresh()
	}
	if (!(await ensure())) return
	// Raven marks the channel read once it is open (its threads stay unread until opened).
	state.value = { ...state.value, unread: 0 }
	drawerOpen.value = true
	chatChanged()
}

watch(() => issueChatStore.openRequest, honourOpenRequest)

watch(
	() => props.issueName,
	() => {
		drawerOpen.value = false
		// Keep `enabled`, so the column and its Raven frame stay while the next Issue loads.
		state.value = { ...EMPTY, enabled: state.value.enabled }
		loading.value = true
		refresh()
	},
	{ immediate: true }
)

watch(
	() => props.status,
	(now, before) => {
		if (before && now !== before) refresh()
	}
)

const channelId = computed(() => (state.value.is_member ? state.value.channel_id : null))
const realtime = useDocRealtime({ doctype: "Raven Channel", name: channelId })
let refreshTimer = null
realtime.on("message_created", (data) => {
	if (data?.channel_id !== channelId.value || drawerOpen.value || docked.value) return
	if (data?.sender === sessionUser()) return
	clearTimeout(refreshTimer)
	refreshTimer = setTimeout(refresh, 300)
})

// A reply in a thread the user takes part in: Raven tells that user directly (#1623).
useUserRealtime("raven:unread_thread_count_updated", () => {
	if (!docked.value && state.value.is_member) refresh()
})

function onKeydown(event) {
	if (event.defaultPrevented || !state.value.enabled) return
	if (event.key.toLowerCase() !== "c" || !isPlainKey(event) || event.shiftKey) return
	if (isTypingTarget(event.target) || insideOverlay(event.target) || dialogOpen()) return
	event.preventDefault()
	if (docked.value) panelRef.value?.focus()
	else onClick()
}

onMounted(() => window.addEventListener("keydown", onKeydown))
onDeactivated(() => {
	drawerOpen.value = false
})
onBeforeUnmount(() => {
	window.removeEventListener("keydown", onKeydown)
	clearTimeout(refreshTimer)
})
</script>
