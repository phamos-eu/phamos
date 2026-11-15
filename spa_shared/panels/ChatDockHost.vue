<template>
	<!-- The chat panel of the dock (#1911): only the place the record's chat lays itself into.
	     The chat itself (IssueChatPanel, owned by IssueChatButton in the record's top bar) keeps
	     its state, its Raven frame and its overlay mode for narrow screens. -->
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

// Provided by DockedPanel: whether the panel is expanded.
const expanded = inject("dockPanelExpanded", ref(true))

// Raven needs 768px for its desktop layout (#1613). Below lg the dock can't give that next to the
// description, so the chat stays the overlay the top-bar button opens, as before.
const wideQuery = typeof window !== "undefined" ? window.matchMedia("(min-width: 1024px)") : null
const wide = ref(Boolean(wideQuery?.matches))
const onWide = () => (wide.value = Boolean(wideQuery?.matches))

const chat = computed(() => issueChatStore.chats[props.recordName])
// Hidden until the chat button said whether this record has a chat at all, and on narrow screens.
const available = computed(() => wide.value && chat.value?.enabled === true)

function publish() {
	issueChatStore.dockHost = {
		record: props.recordName,
		expanded: expanded.value,
		available: available.value,
	}
}

watch([expanded, available, () => props.recordName], publish)
watch(
	[() => chat.value?.summary, available],
	([summary, isAvailable]) => emit("state", { summary: summary || "", hidden: !isAvailable }),
	{ immediate: true }
)

onMounted(() => {
	wideQuery?.addEventListener("change", onWide)
	// After mount: the chat teleports into #issue-chat-host, which must be in the page by then.
	publish()
})

onBeforeUnmount(() => {
	wideQuery?.removeEventListener("change", onWide)
	if (issueChatStore.dockHost?.record === props.recordName) issueChatStore.dockHost = null
})
</script>
