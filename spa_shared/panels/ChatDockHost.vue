<template>
	<!-- The chat panel (#1911, #1915): only the place the record's chat lays itself into. The chat
	     itself (IssueChatPanel, owned by IssueChatButton in the record's top bar) keeps its state
	     and its Raven frame. -->
	<div id="issue-chat-host" class="flex h-full min-h-0 w-full flex-col" />
</template>

<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { issueChatStore } from "@spa/issueChatStore.js"

const props = defineProps({
	recordName: { type: String, required: true },
	embedded: { type: Boolean, default: false },
})
const emit = defineEmits(["state"])

// Provided by PanelBody: whether the panel shows in a tile (not closed to the rail).
const expanded = inject("dockPanelExpanded", ref(true))

const chat = computed(() => issueChatStore.chats[props.recordName])
// The chat lays itself in once the button knows it can (Raven); the tile keeps its place while
// that loads and goes only when there is no chat at all, so the tiles don't shift on load.
const available = computed(() => chat.value?.enabled === true)
const noChat = computed(() => chat.value?.enabled === false)

function publish() {
	issueChatStore.dockHost = {
		record: props.recordName,
		expanded: expanded.value,
		available: available.value,
	}
}

watch([expanded, available, () => props.recordName], publish)
watch(
	[() => chat.value?.summary, () => chat.value?.badge, () => chat.value?.tone, noChat],
	([summary, badge, tone, hidden]) =>
		emit("state", { summary: summary || "", badge: badge || "", tone: tone || "", hidden }),
	{ immediate: true }
)

// After mount: the chat teleports into #issue-chat-host, which must be in the page by then.
onMounted(publish)

onBeforeUnmount(() => {
	if (issueChatStore.dockHost?.record === props.recordName) issueChatStore.dockHost = null
})
</script>
