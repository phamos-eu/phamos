<template>
	<section class="relative flex h-full min-h-0 flex-col overflow-hidden bg-white">
		<div
			class="flex flex-shrink-0 flex-wrap items-center justify-between gap-2 border-b border-gray-200 px-4 py-3"
		>
			<div class="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
				Discussion
			</div>
			<div v-if="channelId && !activeThread" class="flex items-center gap-2">
				<button
					type="button"
					class="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
					@click="showInvite = !showInvite"
				>
					Invite
				</button>
				<a
					:href="ravenUrl"
					target="_blank"
					rel="noopener"
					class="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
				>
					Open in Raven
				</a>
			</div>
		</div>

		<div v-if="!featureEnabled" class="px-4 py-4 text-sm text-gray-500">
			<template v-if="resolvedFlags.raven_unavailable">
				Raven is not installed on this site.
			</template>
			<template v-else>
				Issue chat is disabled. Enable it in phamos Settings.
			</template>
		</div>

		<template v-else>
			<div
				v-if="loading && !channelId"
				class="flex flex-1 items-center justify-center px-4 text-sm text-gray-500"
			>
				Loading…
			</div>

			<div
				v-else-if="!channelId"
				class="flex flex-1 flex-col justify-center gap-3 px-4 py-6"
			>
				<p class="text-sm text-gray-600">
					Start a private Raven channel for this issue. Creator and assignees are added
					automatically.
				</p>
				<div>
					<Button :loading="starting" variant="solid" @click="startDiscussion">
						Start discussion
					</Button>
				</div>
				<p v-if="error" class="text-sm text-red-600">{{ error }}</p>
			</div>

			<div v-else class="relative flex min-h-0 flex-1 flex-col">
				<div
					ref="listEl"
					class="min-h-0 flex-1 space-y-3 overflow-y-auto bg-gray-50 px-3 py-3"
				>
					<div v-if="!messages.length" class="text-center text-sm text-gray-500">
						No messages yet. Say hello.
					</div>
					<button
						v-for="m in messages"
						:key="m.name"
						type="button"
						class="block w-full rounded-md bg-white px-3 py-2 text-left shadow-sm transition hover:ring-1 hover:ring-gray-300"
						@click="openThread(m)"
					>
						<div class="mb-0.5 flex items-baseline justify-between gap-2">
							<span class="text-xs font-semibold text-gray-800">
								{{ m.owner_name || m.owner }}
							</span>
							<span class="flex items-center gap-1.5">
								<span
									v-if="m.is_thread"
									class="rounded-full bg-violet-50 px-1.5 py-0.5 text-[10px] font-semibold text-violet-700"
								>
									Thread
								</span>
								<span class="text-[11px] text-gray-400">{{ formatTime(m.creation) }}</span>
							</span>
						</div>
						<div
							v-if="m.is_reply && m.reply_preview"
							class="mb-1 border-l-2 border-gray-300 pl-2 text-[11px] text-gray-500"
						>
							{{ m.reply_preview }}
						</div>
						<div
							class="whitespace-pre-wrap text-sm text-gray-800"
							v-html="renderText(m.text)"
						></div>
					</button>
				</div>

				<div v-if="showInvite" class="border-t border-gray-200 bg-white px-3 py-2">
					<div class="mb-2 text-xs font-medium text-gray-600">Invite Raven users</div>
					<div class="mb-2 max-h-28 overflow-y-auto rounded border border-gray-200 p-1">
						<label
							v-for="u in inviteUsers"
							:key="u.user"
							class="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-gray-50"
						>
							<input
								type="checkbox"
								:checked="inviteSelection.includes(u.user)"
								@change="toggleInvite(u.user)"
							/>
							<span>{{ u.full_name }}</span>
						</label>
					</div>
					<Button size="sm" :loading="inviting" @click="sendInvites">Add to channel</Button>
				</div>

				<form
					class="flex flex-shrink-0 gap-2 border-t border-gray-200 bg-white p-2"
					@submit.prevent="send"
				>
					<input
						v-model="draft"
						type="text"
						class="min-w-0 flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm"
						placeholder="Write a message…"
						:disabled="sending"
					/>
					<Button type="submit" variant="solid" :loading="sending" :disabled="!draft.trim()">
						Send
					</Button>
				</form>
				<p v-if="error && !activeThread" class="px-3 pb-2 text-sm text-red-600">{{ error }}</p>

				<!-- Thread overlay stays inside Discussion column -->
				<div
					v-if="activeThread"
					class="absolute inset-0 z-10 flex flex-col bg-white"
				>
					<div
						class="flex flex-shrink-0 items-center justify-between gap-2 border-b border-gray-200 px-3 py-2"
					>
						<div class="flex min-w-0 items-center gap-2">
							<button
								type="button"
								class="rounded-md px-2 py-1 text-sm text-gray-600 hover:bg-gray-100"
								@click="closeThread"
							>
								← Back
							</button>
							<span class="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
								Thread
							</span>
						</div>
						<a
							v-if="threadRavenUrl"
							:href="threadRavenUrl"
							target="_blank"
							rel="noopener"
							class="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
						>
							Open in Raven
						</a>
					</div>

					<div
						v-if="threadRoot"
						class="flex-shrink-0 border-b border-gray-100 bg-gray-50 px-3 py-3"
					>
						<div class="mb-0.5 flex items-baseline justify-between gap-2">
							<span class="text-xs font-semibold text-gray-800">
								{{ threadRoot.owner_name || threadRoot.owner }}
							</span>
							<span class="text-[11px] text-gray-400">
								{{ formatTime(threadRoot.creation) }}
							</span>
						</div>
						<div
							class="whitespace-pre-wrap text-sm text-gray-800"
							v-html="renderText(threadRoot.text)"
						></div>
					</div>

					<div
						ref="threadListEl"
						class="min-h-0 flex-1 space-y-2 overflow-y-auto bg-gray-50 px-3 py-3"
					>
						<div
							v-if="threadLoading && !threadMessages.length"
							class="text-center text-sm text-gray-500"
						>
							Loading…
						</div>
						<div
							v-else-if="!threadMessages.length"
							class="text-center text-sm text-gray-500"
						>
							No replies yet. Click a message below to answer, or write a reply.
						</div>
						<button
							v-for="m in threadMessages"
							:key="m.name"
							type="button"
							class="block w-full rounded-md bg-white px-3 py-2 text-left shadow-sm transition hover:ring-1 hover:ring-gray-300"
							:class="{ 'ring-1 ring-blue-400': replyTo?.name === m.name }"
							@click="setReplyTo(m)"
						>
							<div class="mb-0.5 flex items-baseline justify-between gap-2">
								<span class="text-xs font-semibold text-gray-800">
									{{ m.owner_name || m.owner }}
								</span>
								<span class="text-[11px] text-gray-400">{{ formatTime(m.creation) }}</span>
							</div>
							<div
								v-if="m.is_reply && m.reply_preview"
								class="mb-1 border-l-2 border-gray-300 pl-2 text-[11px] text-gray-500"
							>
								{{ m.reply_preview }}
							</div>
							<div
								class="whitespace-pre-wrap text-sm text-gray-800"
								v-html="renderText(m.text)"
							></div>
						</button>
					</div>

					<div class="flex-shrink-0 border-t border-gray-200 bg-white p-2">
						<div
							v-if="replyTo"
							class="mb-2 flex items-center justify-between gap-2 rounded-md bg-blue-50 px-2 py-1.5 text-xs text-blue-800"
						>
							<span class="min-w-0 truncate">
								Replying to {{ replyTo.owner_name || replyTo.owner }}
							</span>
							<button
								type="button"
								class="flex-shrink-0 font-medium hover:underline"
								@click="replyTo = null"
							>
								Clear
							</button>
						</div>
						<form class="flex gap-2" @submit.prevent="sendThread">
							<input
								v-model="threadDraft"
								type="text"
								class="min-w-0 flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm"
								:placeholder="replyTo ? 'Write a reply…' : 'Reply in thread…'"
								:disabled="threadSending"
							/>
							<Button
								type="submit"
								variant="solid"
								:loading="threadSending"
								:disabled="!threadDraft.trim()"
							>
								Send
							</Button>
						</form>
						<p v-if="error" class="mt-1 text-sm text-red-600">{{ error }}</p>
					</div>
				</div>
			</div>
		</template>
	</section>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue"
import { call } from "frappe-ui"

const props = defineProps({
	issueName: { type: String, required: true },
	chatFlags: {
		type: Object,
		default: () => ({
			raven_installed: false,
			enabled: false,
			raven_unavailable: true,
		}),
	},
	flags: {
		type: Object,
		default: null,
	},
})

const API = "phamos.api.i_own_my_work"

const loading = ref(false)
const starting = ref(false)
const sending = ref(false)
const inviting = ref(false)
const error = ref("")
const channelId = ref(null)
const messages = ref([])
const members = ref([])
const ravenUrl = ref("")
const draft = ref("")
const showInvite = ref(false)
const inviteUsers = ref([])
const inviteSelection = ref([])
const listEl = ref(null)

const activeThread = ref(null)
const threadRoot = ref(null)
const threadMessages = ref([])
const threadRavenUrl = ref("")
const threadDraft = ref("")
const threadSending = ref(false)
const threadLoading = ref(false)
const replyTo = ref(null)
const threadListEl = ref(null)

let pollTimer = null
let threadPollTimer = null

const resolvedFlags = computed(() => props.flags || props.chatFlags || {})
const featureEnabled = computed(() => !!resolvedFlags.value?.enabled)

function formatTime(value) {
	if (!value) return ""
	try {
		return new Date(value).toLocaleString()
	} catch (e) {
		return value
	}
}

function renderText(text) {
	if (!text) return ""
	const escaped = String(text)
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
	return escaped
		.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
		.replace(
			/\[([^\]]+)\]\((https?:\/\/[^\s)]+|\/[^\s)]+)\)/g,
			'<a class="text-blue-600 underline" href="$2" target="_blank" rel="noopener">$1</a>'
		)
		.replace(/\n/g, "<br>")
}

async function scrollToBottom() {
	await nextTick()
	if (listEl.value) {
		listEl.value.scrollTop = listEl.value.scrollHeight
	}
}

async function scrollThreadToBottom() {
	await nextTick()
	if (threadListEl.value) {
		threadListEl.value.scrollTop = threadListEl.value.scrollHeight
	}
}

async function loadChat() {
	if (!featureEnabled.value || !props.issueName) return
	loading.value = true
	error.value = ""
	try {
		const data = await call(`${API}.get_issue_chat`, { name: props.issueName })
		channelId.value = data.channel_id || null
		messages.value = data.messages || []
		members.value = data.members || []
		ravenUrl.value =
			data.raven_url || (channelId.value ? `/raven/channel/${channelId.value}` : "")
		await scrollToBottom()
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load chat"
	} finally {
		loading.value = false
	}
}

async function startDiscussion() {
	starting.value = true
	error.value = ""
	try {
		const data = await call(`${API}.ensure_issue_channel`, { name: props.issueName })
		channelId.value = data.channel_id
		messages.value = data.messages || []
		members.value = data.members || []
		ravenUrl.value = data.raven_url || `/raven/channel/${data.channel_id}`
		await scrollToBottom()
		startPolling()
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not start discussion"
	} finally {
		starting.value = false
	}
}

async function refreshMessages() {
	if (!channelId.value || activeThread.value) return
	try {
		const data = await call(`${API}.get_chat_messages`, {
			channel_id: channelId.value,
			limit: 50,
			issue_name: props.issueName,
		})
		const next = data.messages || []
		const prevLast = messages.value[messages.value.length - 1]?.name
		const nextLast = next[next.length - 1]?.name
		messages.value = next
		if (prevLast !== nextLast) await scrollToBottom()
	} catch (e) {
		/* keep panel usable while polling */
	}
}

async function send() {
	const text = draft.value.trim()
	if (!text || !channelId.value) return
	sending.value = true
	error.value = ""
	try {
		const msg = await call(`${API}.send_chat_message`, {
			channel_id: channelId.value,
			text,
			issue_name: props.issueName,
		})
		draft.value = ""
		messages.value = [...messages.value, msg]
		await scrollToBottom()
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not send message"
	} finally {
		sending.value = false
	}
}

async function openThread(message) {
	if (!message?.name) return
	threadLoading.value = true
	error.value = ""
	replyTo.value = null
	threadDraft.value = ""
	try {
		const data = await call(`${API}.open_or_create_thread`, {
			message_id: message.name,
			issue_name: props.issueName,
		})
		activeThread.value = data.thread_id
		threadRoot.value = data.root_message
		threadMessages.value = (data.messages || []).filter((m) => m.name !== data.thread_id)
		threadRavenUrl.value = data.raven_url || `/raven/channel/${data.thread_id}`
		// Mark parent message as thread in local list
		messages.value = messages.value.map((m) =>
			m.name === message.name ? { ...m, is_thread: 1 } : m
		)
		await scrollThreadToBottom()
		startThreadPolling()
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not open thread"
		activeThread.value = null
	} finally {
		threadLoading.value = false
	}
}

function closeThread() {
	stopThreadPolling()
	activeThread.value = null
	threadRoot.value = null
	threadMessages.value = []
	threadRavenUrl.value = ""
	replyTo.value = null
	threadDraft.value = ""
	error.value = ""
	refreshMessages()
}

function setReplyTo(message) {
	replyTo.value = message
}

async function refreshThread() {
	if (!activeThread.value) return
	try {
		const data = await call(`${API}.get_thread`, {
			thread_id: activeThread.value,
			issue_name: props.issueName,
		})
		if (data.root_message) threadRoot.value = data.root_message
		const next = (data.messages || []).filter((m) => m.name !== activeThread.value)
		const prevLast = threadMessages.value[threadMessages.value.length - 1]?.name
		const nextLast = next[next.length - 1]?.name
		threadMessages.value = next
		if (prevLast !== nextLast) await scrollThreadToBottom()
	} catch (e) {
		/* keep overlay usable while polling */
	}
}

async function sendThread() {
	const text = threadDraft.value.trim()
	if (!text || !activeThread.value) return
	threadSending.value = true
	error.value = ""
	try {
		const args = {
			channel_id: activeThread.value,
			text,
			issue_name: props.issueName,
		}
		if (replyTo.value?.name) {
			args.is_reply = 1
			args.linked_message = replyTo.value.name
		}
		const msg = await call(`${API}.send_chat_message`, args)
		threadDraft.value = ""
		replyTo.value = null
		threadMessages.value = [...threadMessages.value, msg]
		await scrollThreadToBottom()
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not send reply"
	} finally {
		threadSending.value = false
	}
}

async function loadInviteUsers() {
	try {
		inviteUsers.value = await call(`${API}.get_raven_users_for_invite`)
	} catch (e) {
		inviteUsers.value = []
	}
}

function toggleInvite(user) {
	if (inviteSelection.value.includes(user)) {
		inviteSelection.value = inviteSelection.value.filter((u) => u !== user)
	} else {
		inviteSelection.value = [...inviteSelection.value, user]
	}
}

async function sendInvites() {
	if (!inviteSelection.value.length) return
	inviting.value = true
	error.value = ""
	try {
		const data = await call(`${API}.invite_to_issue_channel`, {
			name: props.issueName,
			users: inviteSelection.value,
		})
		members.value = data.members || []
		inviteSelection.value = []
		showInvite.value = false
		if (data.skipped?.length) {
			error.value = `Skipped (not Raven users): ${data.skipped.join(", ")}`
		}
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not invite"
	} finally {
		inviting.value = false
	}
}

function startPolling() {
	stopPolling()
	if (!channelId.value) return
	pollTimer = setInterval(refreshMessages, 5000)
}

function stopPolling() {
	if (pollTimer) {
		clearInterval(pollTimer)
		pollTimer = null
	}
}

function startThreadPolling() {
	stopThreadPolling()
	if (!activeThread.value) return
	threadPollTimer = setInterval(refreshThread, 5000)
}

function stopThreadPolling() {
	if (threadPollTimer) {
		clearInterval(threadPollTimer)
		threadPollTimer = null
	}
}

watch(
	() => props.issueName,
	async () => {
		stopPolling()
		closeThread()
		channelId.value = null
		messages.value = []
		await loadChat()
		if (channelId.value) startPolling()
	}
)

watch(showInvite, (open) => {
	if (open) loadInviteUsers()
})

onMounted(async () => {
	await loadChat()
	if (channelId.value) startPolling()
})

onUnmounted(() => {
	stopPolling()
	stopThreadPolling()
})
</script>
