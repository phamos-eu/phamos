<template>
	<span
		v-if="state"
		class="inline-flex flex-none items-center gap-0.5 rounded px-1 text-xs"
		:class="state.unread ? 'text-ink-red-4 hover:bg-surface-red-1' : 'text-ink-gray-5 hover:bg-surface-gray-3'"
		:title="title"
		:aria-label="title"
		@click.stop="open"
	>
		<FeatherIcon name="message-circle" class="h-3.5 w-3.5" />
		<span v-if="state.unread" class="font-semibold tabular-nums">{{ state.unread > 99 ? "99+" : state.unread }}</span>
	</span>
</template>

<script setup>
// Chat icon on an Issue row or card (#1617). Clicking it opens the Issue with its chat drawer.
// A span, not a button: it sits inside the row's own button.
import { computed } from "vue"
import { FeatherIcon } from "frappe-ui"
import { requestChatOpen } from "@spa/issueChatStore.js"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	issueName: { type: String, required: true },
	/** { channel_id, is_member, archived, unread } or undefined when there is no chat */
	state: { type: Object, default: null },
})
const emit = defineEmits(["open"])

const title = computed(() => {
	if (!props.state) return ""
	if (props.state.unread === 1) return __("1 unread message in the chat")
	if (props.state.unread) return __("{0} unread messages in the chat", [props.state.unread])
	return props.state.archived ? __("Chat (read-only)") : __("Open the chat")
})

function open() {
	requestChatOpen(props.issueName)
	emit("open", props.issueName)
}
</script>
