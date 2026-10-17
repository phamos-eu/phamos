<template>
	<template v-if="state.enabled">
		<Button
			:variant="state.is_member ? 'subtle' : 'outline'"
			:loading="busy"
			:title="buttonTitle"
			@click="onClick"
		>
			<template #prefix><FeatherIcon name="message-circle" class="h-3.5 w-3.5" /></template>
			{{ buttonLabel }}
			<template v-if="state.unread" #suffix>
				<span
					class="ml-0.5 inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-surface-red-5 px-1 text-[10px] font-semibold text-ink-white"
					:aria-label="__('{0} unread', [state.unread])"
				>
					{{ state.unread > 99 ? "99+" : state.unread }}
				</span>
			</template>
		</Button>
		<IssueChatPanel
			v-if="state.url"
			v-model:open="drawerOpen"
			:record-name="issueName"
			:url="state.url"
			:title="`${issueName}: ${subject || ''}`"
			:skipped-users="state.skipped_users || []"
			@closed="refresh"
		/>
	</template>
</template>

<script setup>
// "Chat" on an Issue (#1615): shows whether the Issue has a Raven chat and how many messages are
// unread, starts or joins it, and opens it in the drawer. "C" toggles the drawer. The unread count
// follows Raven's message_created events in the channel's document room.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { Button, call, FeatherIcon, toast } from "frappe-ui"
import IssueChatPanel from "@spa/components/IssueChatPanel.vue"
import { useDocRealtime } from "@spa/composables/useDocRealtime.js"
import { sessionUser } from "@spa/session.js"
import { __ } from "@spa/utils/i18n.js"
import { dialogOpen, insideOverlay, isPlainKey, isTypingTarget } from "@spa/utils/shortcuts.js"

const props = defineProps({
	issueName: { type: String, required: true },
	subject: { type: String, default: "" },
	// Closing or reopening the Issue archives or restores its chat (#1622).
	status: { type: String, default: "" },
	api: { type: String, required: true },
})

const EMPTY = { enabled: false, channel_id: null, url: null, is_member: false, archived: false, unread: 0, skipped_users: [] }
const state = ref({ ...EMPTY })
const busy = ref(false)
const drawerOpen = ref(false)

const buttonLabel = computed(() => {
	if (!state.value.channel_id) return __("Start chat")
	if (!state.value.is_member) return __("Join chat")
	return __("Chat")
})
const buttonTitle = computed(() => {
	if (!state.value.channel_id) return __("Start a Raven chat with the people on this Issue (C)")
	if (!state.value.is_member) return __("Join the Raven chat of this Issue (C)")
	if (state.value.archived) return __("Read the chat of this closed Issue (C)")
	return __("Open the Raven chat of this Issue (C)")
})

function errorText(e) {
	return e?.messages?.[0] || e?.message || __("Something went wrong")
}

async function refresh() {
	const name = props.issueName
	try {
		const result = await call(`${props.api}.get_issue_chat`, { name })
		if (name === props.issueName) state.value = { ...EMPTY, ...result }
	} catch (e) {
		// The chat is an add-on to the Issue; without it the button just stays hidden.
		if (name === props.issueName) state.value = { ...EMPTY }
	}
}

async function onClick() {
	if (drawerOpen.value) {
		drawerOpen.value = false
		return refresh()
	}
	if (!state.value.channel_id || !state.value.is_member) {
		busy.value = true
		try {
			state.value = { ...EMPTY, ...(await call(`${props.api}.ensure_issue_chat`, { name: props.issueName })) }
		} catch (e) {
			toast({ title: errorText(e), icon: "x-circle", iconClasses: "text-ink-red-4" })
			return
		} finally {
			busy.value = false
		}
	}
	// Raven marks the channel read once it is open.
	state.value = { ...state.value, unread: 0 }
	drawerOpen.value = true
}

watch(
	() => props.issueName,
	() => {
		drawerOpen.value = false
		state.value = { ...EMPTY }
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
	if (data?.channel_id !== channelId.value || drawerOpen.value) return
	if (data?.sender === sessionUser()) return
	clearTimeout(refreshTimer)
	refreshTimer = setTimeout(refresh, 300)
})

function onKeydown(event) {
	if (event.defaultPrevented || !state.value.enabled) return
	if (event.key.toLowerCase() !== "c" || !isPlainKey(event) || event.shiftKey) return
	if (isTypingTarget(event.target) || insideOverlay(event.target) || dialogOpen()) return
	event.preventDefault()
	onClick()
}

onMounted(() => window.addEventListener("keydown", onKeydown))
onBeforeUnmount(() => {
	window.removeEventListener("keydown", onKeydown)
	clearTimeout(refreshTimer)
})
</script>
