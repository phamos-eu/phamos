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
					class="ml-0.5 inline-flex h-4 min-w-[1rem] items-center justify-center gap-0.5 rounded-full px-1 text-[10px] font-semibold text-ink-white"
					:class="unreadTone(state) === 'mention' ? 'bg-surface-red-5' : 'bg-surface-blue-3'"
					:aria-label="unreadSummary(state)"
				>
					{{ unreadTotal > 99 ? "99+" : unreadTotal }}
					<RavenMentionIcon v-if="unreadTone(state) === 'mention'" class="h-2.5 w-2.5" />
				</span>
			</template>
		</Button>
		<IssueChatPanel
			ref="panelRef"
			v-model:open="drawerOpen"
			:record-name="recordName"
			:url="state.is_member ? state.url || '' : ''"
			:title="`${recordName}: ${subject || ''}`"
			:skipped-users="state.is_member ? state.skipped_users || [] : []"
			:threads="state.is_member ? state.threads || [] : []"
			:mention-note="texts.mentionNote"
			@closed="onPanelClosed"
			@thread-opened="onThreadOpened"
		>
			<template #placeholder>
				<FeatherIcon name="message-circle" class="h-8 w-8 text-ink-gray-4" />
				<template v-if="loading">
					<p class="text-sm text-ink-gray-5">{{ __("Loading the chat…") }}</p>
				</template>
				<template v-else-if="!state.channel_id">
					<p class="text-sm font-medium text-ink-gray-8">{{ texts.noChat }}</p>
					<p class="max-w-xs text-xs text-ink-gray-5">{{ texts.startHint }}</p>
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
// The chat of an Issue or a Task (#1615, #1779). Where the view offers a chat column (the Issue view
// from lg on), the chat is always there: the chat itself, or "Start chat" / "Join chat". Elsewhere
// (narrow screens, the Tasks Gantt) this button shows whether there is a chat and how many
// messages are unread, and opens it as an overlay. The unread count follows Raven's
// message_created events in the channel's document room.
import { computed, nextTick, onBeforeUnmount, onDeactivated, ref, watch } from "vue"
import { Button, call, FeatherIcon, toast } from "frappe-ui"
import RavenMentionIcon from "@spa/components/RavenMentionIcon.vue"
import IssueChatPanel from "@spa/components/IssueChatPanel.vue"
import { useDocRealtime } from "@spa/composables/useDocRealtime.js"
import { sessionUser } from "@spa/session.js"
import { __ } from "@spa/utils/i18n.js"
import { chatChanged, issueChatStore } from "@spa/issueChatStore.js"
import { useUserRealtime } from "@spa/composables/useUserRealtime.js"
import { totalUnread, unreadSummary, unreadTone } from "@spa/utils/chatUnread.js"

const props = defineProps({
	/** "Issue" or "Task": picks the cockpit endpoints (get_issue_chat, get_task_chat …) and texts */
	doctype: { type: String, default: "Issue" },
	recordName: { type: String, required: true },
	subject: { type: String, default: "" },
	// Closing or reopening the record archives or restores its chat (#1622, #1779).
	status: { type: String, default: "" },
	api: { type: String, required: true },
})

const method = computed(() => ({
	get: `${props.api}.get_${props.doctype.toLowerCase()}_chat`,
	ensure: `${props.api}.ensure_${props.doctype.toLowerCase()}_chat`,
}))

// Whole sentences per record type, so each translates on its own.
const texts = computed(() =>
	props.doctype === "Task"
		? {
				noChat: __("No chat for this Task yet."),
				startHint: __("Start one with the people on this Task. Messages also show up in Raven, linked to the Task."),
				start: __("Start a Raven chat with the people on this Task"),
				join: __("Join the Raven chat of this Task"),
				closed: __("Read the chat of this finished Task"),
				open: __("Open the Raven chat of this Task"),
				mentionNote: __("When you send, everyone mentioned who can read this Task joins the chat and is assigned to it."),
			}
		: {
				noChat: __("No chat for this Issue yet."),
				startHint: __("Start one with the people on this Issue. Messages also show up in Raven, linked to the Issue."),
				start: __("Start a Raven chat with the people on this Issue"),
				join: __("Join the Raven chat of this Issue"),
				closed: __("Read the chat of this closed Issue"),
				open: __("Open the Raven chat of this Issue"),
				mentionNote: __("When you send, everyone mentioned who can read this Issue joins the chat and is assigned to it."),
			}
)

const EMPTY = { enabled: false, channel_id: null, url: null, is_member: false, archived: false, unread: 0, unread_threads: 0, mentions: 0, threads: [], skipped_users: [] }
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
	if (!state.value.channel_id) return texts.value.start
	if (!state.value.is_member) return texts.value.join
	const base = state.value.archived ? texts.value.closed : texts.value.open
	const unread = unreadSummary(state.value)
	return unread ? `${base} · ${unread}` : base
})

function errorText(e) {
	return e?.messages?.[0] || e?.message || __("Something went wrong")
}

async function refresh() {
	const name = props.recordName
	try {
		const result = await call(method.value.get, { name })
		if (name !== props.recordName) return
		state.value = { ...EMPTY, ...result }
		honourOpenRequest()
	} catch (e) {
		// The chat is an add-on to the record; without it the button just stays hidden.
		if (name === props.recordName) state.value = { ...EMPTY }
	} finally {
		if (name === props.recordName) loading.value = false
	}
}

// The user is reading that thread now: drop it from the hint at once. Raven saves the read mark
// a little later (debounced, as the user scrolls), so the server is asked again after a while;
// if Raven did not record the visit, the thread comes back.
function onThreadOpened(threadId) {
	const opened = (state.value.threads || []).find((t) => t.thread_id === threadId)
	if (opened) {
		state.value = {
			...state.value,
			threads: state.value.threads.filter((t) => t.thread_id !== threadId),
			unread_threads: Math.max(0, (state.value.unread_threads || 0) - (opened.unread || 0)),
		}
	}
	clearTimeout(refreshTimer)
	refreshTimer = setTimeout(refresh, 5000)
	chatChanged()
}

function onPanelClosed() {
	chatChanged()
	refresh()
}

// The chat icon in a list asked for this record's chat (issueChatStore.openRequest).
async function honourOpenRequest() {
	// Wait for this record's state; refresh() calls again once it is loaded.
	if (issueChatStore.openRequest !== props.recordName || !state.value.channel_id) return
	// Let the panel mount first: only then is it known whether the chat is a column.
	await nextTick()
	if (issueChatStore.openRequest !== props.recordName) return
	const target = issueChatStore.openTarget
	if (docked.value) {
		// The column already shows the chat; go to the message the list pointed at.
		issueChatStore.openRequest = null
		issueChatStore.openTarget = null
		await nextTick()
		panelRef.value?.focusTarget(target)
		return
	}
	// Only the button on the page takes it, not a kept-alive copy.
	await nextTick()
	const el = buttonRef.value?.$el
	if (!el?.isConnected || el.offsetParent === null) return
	if (issueChatStore.openRequest !== props.recordName) return
	issueChatStore.openRequest = null
	issueChatStore.openTarget = null
	if (!drawerOpen.value) await onClick()
	await nextTick()
	panelRef.value?.focusTarget(target)
}

/** Start or join the chat; true when the user is in it afterwards. */
async function ensure() {
	if (state.value.channel_id && state.value.is_member) return true
	const name = props.recordName
	busy.value = true
	try {
		const result = await call(method.value.ensure, { name })
		// Another record was opened meanwhile: its chat must not show this one's (#1794).
		if (name !== props.recordName) return false
		state.value = { ...EMPTY, ...result }
		chatChanged()
		return true
	} catch (e) {
		if (name === props.recordName) toast({ title: errorText(e), icon: "x-circle", iconClasses: "text-ink-red-4" })
		return false
	} finally {
		if (name === props.recordName) busy.value = false
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
	() => props.recordName,
	() => {
		drawerOpen.value = false
		busy.value = false
		// Keep `enabled`, so the column and its Raven frame stay while the next record loads.
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
	if (state.value.is_member) refresh()
})

onDeactivated(() => {
	drawerOpen.value = false
})
onBeforeUnmount(() => clearTimeout(refreshTimer))
</script>
