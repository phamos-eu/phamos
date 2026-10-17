<template>
	<span
		v-if="state"
		class="inline-flex flex-none items-center gap-0.5 rounded px-1 text-xs"
		:class="total ? 'text-ink-red-4 hover:bg-surface-red-1' : 'text-ink-gray-5 hover:bg-surface-gray-3'"
		:title="title"
		:aria-label="title"
		@click.stop="open"
	>
		<FeatherIcon name="message-circle" class="h-3.5 w-3.5" />
		<span v-if="total" class="font-semibold tabular-nums">{{ total > 99 ? "99+" : total }}</span>
		<!-- Some of it is in threads, which Raven's channel view does not mark (#1623). -->
		<FeatherIcon v-if="state.unread_threads" name="corner-down-right" class="h-3 w-3" />
	</span>
</template>

<script setup>
// Chat icon on an Issue row or card (#1617). Clicking it opens the Issue with its chat drawer.
// A span, not a button: it sits inside the row's own button.
import { computed } from "vue"
import { FeatherIcon } from "frappe-ui"
import { requestChatOpen } from "@spa/issueChatStore.js"
import { totalUnread, unreadSummary } from "@spa/utils/chatUnread.js"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	issueName: { type: String, required: true },
	/** { channel_id, is_member, archived, unread, unread_threads }, or none when there is no chat */
	state: { type: Object, default: null },
})
const emit = defineEmits(["open"])

const total = computed(() => totalUnread(props.state))
const title = computed(() => {
	if (!props.state) return ""
	return unreadSummary(props.state) || (props.state.archived ? __("Chat (read-only)") : __("Open the chat"))
})

function open() {
	requestChatOpen(props.issueName)
	emit("open", props.issueName)
}
</script>
