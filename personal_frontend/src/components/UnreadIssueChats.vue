<template>
	<!-- Unread Issue chats on My Day (#1618): pinned while there is something to read. -->
	<section
		v-if="chats.length"
		class="rounded-lg border border-outline-gray-2 bg-surface-white shadow-sm"
		:aria-label="__('Unread Issue chats')"
	>
		<header class="flex items-center gap-2 px-3 pt-2 text-xs font-semibold uppercase tracking-wide text-ink-gray-6">
			<FeatherIcon name="message-circle" class="h-3.5 w-3.5" />
			{{ __("Unread Issue chats") }}
			<span v-if="total > chats.length" class="font-normal normal-case tracking-normal text-ink-gray-5">
				{{ __("{0} of {1}", [chats.length, total]) }}
			</span>
		</header>
		<ul class="divide-y divide-outline-gray-1 py-1">
			<li v-for="chat in chats" :key="chat.name">
				<button
					type="button"
					class="flex w-full items-center gap-3 px-3 py-1.5 text-left hover:bg-surface-gray-2 focus:outline-none focus-visible:bg-surface-gray-3"
					:title="unreadSummary(chat)"
					@click="open(chat)"
				>
					<span class="flex-none text-xs font-semibold text-ink-gray-5">{{ chat.name }}</span>
					<span class="min-w-0 flex-1 truncate text-sm font-medium text-ink-gray-9">{{ chat.subject }}</span>
					<span v-if="chat.last_sender" class="hidden flex-none truncate text-xs text-ink-gray-5 sm:inline">
						{{ chat.last_sender }} · {{ when(chat.last_activity) }}
					</span>
					<span class="inline-flex flex-none items-center gap-0.5 rounded-full bg-surface-red-5 px-1.5 text-xs font-semibold text-ink-white">
						{{ totalUnread(chat) > 99 ? "99+" : totalUnread(chat) }}
						<FeatherIcon v-if="chat.unread_threads" name="corner-down-right" class="h-3 w-3" />
					</span>
				</button>
			</li>
		</ul>
	</section>
</template>

<script setup>
// Opening an entry opens the Issue with its chat at the first new message, or at the thread with
// the newest reply (the same jump as the chat bubble in the Issue list, #1617).
import { onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { call, FeatherIcon } from "frappe-ui"
import { useRavenUnreadEvents } from "@spa/composables/useRavenUnreadEvents.js"
import { issueChatStore, requestChatOpen } from "@spa/issueChatStore.js"
import { totalUnread, unreadSummary } from "@spa/utils/chatUnread.js"
import { formatDate, isSameCalendarDate, parseSystemDatetimeToUserDate, userLocale } from "@spa/utils/datetime.js"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "@/config"

const router = useRouter()
const chats = ref([])
const total = ref(0)

async function load() {
	try {
		const result = await call(`${spaConfig.api}.get_unread_issue_chats`, { limit: 5 })
		chats.value = result?.chats || []
		total.value = result?.total || 0
	} catch (e) {
		// A hint, not the page: without Raven or the chat feature it stays away.
		chats.value = []
		total.value = 0
	}
}

function when(value) {
	if (!value) return ""
	const date = parseSystemDatetimeToUserDate(String(value))
	// The parsed date already holds the user's wall-clock time; format it as it is.
	return date && isSameCalendarDate(date, new Date())
		? date.toLocaleTimeString(userLocale(), { hour: "2-digit", minute: "2-digit" })
		: formatDate(String(value))
}

function open(chat) {
	requestChatOpen(chat.name, { messageId: chat.first_unread || null, threadId: chat.first_unread_thread || null })
	router.push({ name: "IssueDetail", params: { name: chat.name } })
}

useRavenUnreadEvents(load)
watch(() => issueChatStore.version, load)
onMounted(() => {
	load()
	window.addEventListener("focus", load)
})
onBeforeUnmount(() => window.removeEventListener("focus", load))
</script>
