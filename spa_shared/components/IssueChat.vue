<template>
	<section class="relative flex h-full min-h-0 flex-col overflow-hidden bg-white dark:bg-gray-900">
		<div
			class="flex flex-shrink-0 flex-wrap items-center justify-between gap-2 border-b border-gray-200 px-4 py-3 dark:border-gray-800"
		>
			<div class="text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
				Discussion
			</div>
			<div v-if="channelId && !activeThread" class="flex items-center gap-2">
				<button
					type="button"
					class="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
					@click="showInvite = !showInvite"
				>
					Invite
				</button>
				<a
					:href="ravenUrl"
					target="_blank"
					rel="noopener"
					class="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
				>
					Open in Raven
				</a>
			</div>
		</div>

		<div v-if="!featureEnabled" class="px-4 py-4 text-sm text-gray-500 dark:text-gray-400">
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
				class="flex flex-1 items-center justify-center px-4 text-sm text-gray-500 dark:text-gray-400"
			>
				Loading…
			</div>

			<div
				v-else-if="!channelId"
				class="flex flex-1 flex-col justify-center gap-3 px-4 py-6"
			>
				<p class="text-sm text-gray-600 dark:text-gray-400">
					Start a private Raven channel for this issue. Creator and assignees are added
					automatically.
				</p>
				<div>
					<Button :loading="starting" variant="solid" @click="startDiscussion">
						Start discussion
					</Button>
				</div>
				<p v-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
			</div>

			<div v-else class="relative flex min-h-0 flex-1 flex-col">
				<div
					ref="listEl"
					class="min-h-0 flex-1 space-y-3 overflow-y-auto bg-gray-50 px-3 py-3 dark:bg-gray-950"
				>
					<div v-if="!messages.length" class="text-center text-sm text-gray-500 dark:text-gray-400">
						No messages yet. Say hello.
					</div>
					<button
						v-for="m in messages"
						:key="m.name"
						type="button"
						class="block w-full rounded-md bg-white px-3 py-2 text-left shadow-sm transition hover:ring-1 hover:ring-gray-300 dark:bg-gray-900 dark:hover:ring-gray-600"
						@click="openThread(m)"
					>
						<div class="mb-0.5 flex items-baseline justify-between gap-2">
							<span class="text-xs font-semibold text-gray-800 dark:text-gray-200">
								{{ m.owner_name || m.owner }}
							</span>
							<span class="flex items-center gap-1.5">
								<span
									v-if="m.is_thread"
									class="rounded-full bg-violet-50 px-1.5 py-0.5 text-[10px] font-semibold text-violet-700 dark:bg-violet-950 dark:text-violet-300"
								>
									Thread
								</span>
								<span class="text-[11px] text-gray-400">{{ formatTime(m.creation) }}</span>
							</span>
						</div>
						<div
							v-if="m.is_reply && m.reply_preview"
							class="mb-1 border-l-2 border-gray-300 pl-2 text-[11px] text-gray-500 dark:border-gray-600 dark:text-gray-400"
						>
							{{ m.reply_preview }}
						</div>
						<div
							class="whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200"
							v-html="renderText(m.text)"
						></div>
					</button>
				</div>

				<div v-if="showInvite" class="border-t border-gray-200 bg-white px-3 py-2 dark:border-gray-800 dark:bg-gray-900">
					<div class="mb-2 text-xs font-medium text-gray-600 dark:text-gray-400">Invite Raven users</div>
					<div class="mb-2 max-h-28 overflow-y-auto rounded border border-gray-200 p-1 dark:border-gray-700">
						<label
							v-for="u in inviteUsers"
							:key="u.user"
							class="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
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
					class="flex flex-shrink-0 gap-2 border-t border-gray-200 bg-white p-2 dark:border-gray-800 dark:bg-gray-900"
					@submit.prevent="send"
				>
					<input
						v-model="draft"
						type="text"
						class="min-w-0 flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
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
					class="absolute inset-0 z-10 flex flex-col bg-white dark:bg-gray-900"
				>
					<div
						class="flex flex-shrink-0 items-center justify-between gap-2 border-b border-gray-200 px-3 py-2 dark:border-gray-800"
					>
						<div class="flex min-w-0 items-center gap-2">
							<button
								type="button"
								class="rounded-md px-2 py-1 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
								@click="closeThread"
							>
								← Back
							</button>
							<span class="text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
								Thread
							</span>
						</div>
						<a
							v-if="threadRavenUrl"
							:href="threadRavenUrl"
							target="_blank"
							rel="noopener"
							class="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
						>
							Open in Raven
						</a>
					</div>

					<div
						v-if="threadRoot"
						class="flex-shrink-0 border-b border-gray-100 bg-gray-50 px-3 py-3 dark:border-gray-800 dark:bg-gray-950"
					>
						<div class="mb-0.5 flex items-baseline justify-between gap-2">
							<span class="text-xs font-semibold text-gray-800 dark:text-gray-200">
								{{ threadRoot.owner_name || threadRoot.owner }}
							</span>
							<span class="text-[11px] text-gray-400">
								{{ formatTime(threadRoot.creation) }}
							</span>
						</div>
						<div
							class="whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200"
							v-html="renderText(threadRoot.text)"
						></div>
					</div>

					<div
						ref="threadListEl"
						class="min-h-0 flex-1 space-y-2 overflow-y-auto bg-gray-50 px-3 py-3 dark:bg-gray-950"
					>
						<div
							v-if="threadLoading && !threadMessages.length"
							class="text-center text-sm text-gray-500 dark:text-gray-400"
						>
							Loading…
						</div>
						<div
							v-else-if="!threadMessages.length"
							class="text-center text-sm text-gray-500 dark:text-gray-400"
						>
							No replies yet. Click a message below to answer, or write a reply.
						</div>
						<button
							v-for="m in threadMessages"
							:key="m.name"
							type="button"
							class="block w-full rounded-md bg-white px-3 py-2 text-left shadow-sm transition hover:ring-1 hover:ring-gray-300 dark:bg-gray-900 dark:hover:ring-gray-600"
							:class="{ 'ring-1 ring-blue-400': replyTo?.name === m.name }"
							@click="setReplyTo(m)"
						>
							<div class="mb-0.5 flex items-baseline justify-between gap-2">
								<span class="text-xs font-semibold text-gray-800 dark:text-gray-200">
									{{ m.owner_name || m.owner }}
								</span>
								<span class="text-[11px] text-gray-400">{{ formatTime(m.creation) }}</span>
							</div>
							<div
								v-if="m.is_reply && m.reply_preview"
								class="mb-1 border-l-2 border-gray-300 pl-2 text-[11px] text-gray-500 dark:border-gray-600 dark:text-gray-400"
							>
								{{ m.reply_preview }}
							</div>
							<div
								class="whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200"
								v-html="renderText(m.text)"
							></div>
						</button>
					</div>

					<div class="flex-shrink-0 border-t border-gray-200 bg-white p-2 dark:border-gray-800 dark:bg-gray-900">
						<div
							v-if="replyTo"
							class="mb-2 flex items-center justify-between gap-2 rounded-md bg-blue-50 px-2 py-1.5 text-xs text-blue-800 dark:bg-blue-950 dark:text-blue-300"
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
								class="min-w-0 flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
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
import { formatDatetime } from "@spa/utils/datetime"

const props = defineProps({
	issueName: { type: String, default: "" },
	documentName: { type: String, default: "" },
	linkedDoctype: { type: String, default: "Issue" },
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
	apiPrefix: {
		type: String,
		default: "phamos.api.i_own_my_work",
	},
})

const API = computed(() => props.apiPrefix || "phamos.api.i_own_my_work")

const docName = computed(() => props.documentName || props.issueName)
const linkedDoctype = computed(() => props.linkedDoctype || "Issue")

function linkedArgs(extra = {}) {
	return {
		linked_doctype: linkedDoctype.value,
		linked_document: docName.value,
		...extra,
	}
}

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
	return formatDatetime(value)
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
	if (!featureEnabled.value || !docName.value) return
	loading.value = true
	error.value = ""
	try {
		const data = await call(`${API.value}.get_document_chat`, {
			linked_doctype: linkedDoctype.value,
			name: docName.value,
		})
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
		const data = await call(`${API.value}.ensure_document_channel`, {
			linked_doctype: linkedDoctype.value,
			name: docName.value,
		})
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
		const data = await call(`${API.value}.get_chat_messages`, {
			channel_id: channelId.value,
			limit: 50,
			...linkedArgs(),
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
		const msg = await call(`${API.value}.send_chat_message`, {
			channel_id: channelId.value,
			text,
			...linkedArgs(),
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
		const data = await call(`${API.value}.open_or_create_thread`, {
			message_id: message.name,
			...linkedArgs(),
		})
		activeThread.value = data.thread_id
		threadRoot.value = data.root_message
		threadMessages.value = (data.messages || []).filter((m) => m.name !== data.thread_id)
		threadRavenUrl.value = data.raven_url || `/raven/channel/${data.thread_id}`
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
		const data = await call(`${API.value}.get_thread`, {
			thread_id: activeThread.value,
			...linkedArgs(),
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
			...linkedArgs(),
		}
		if (replyTo.value?.name) {
			args.is_reply = 1
			args.linked_message = replyTo.value.name
		}
		const msg = await call(`${API.value}.send_chat_message`, args)
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
		inviteUsers.value = await call(`${API.value}.get_raven_users_for_invite`)
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
		const data = await call(`${API.value}.invite_to_document_channel`, {
			linked_doctype: linkedDoctype.value,
			name: docName.value,
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
	() => [linkedDoctype.value, docName.value],
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
