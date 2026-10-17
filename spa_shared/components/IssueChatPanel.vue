<template>
	<!-- Wide screens: a column of the Issue view (#issue-chat-host in IssuesInbox). Below lg, or
	     where the view has no such column, it covers the page from the right. -->
	<Teleport :to="inColumn ? '#issue-chat-host' : 'body'">
		<Transition
			:enter-active-class="inColumn ? '' : 'transition-transform duration-200 ease-out'"
			:enter-from-class="inColumn ? '' : 'translate-x-full'"
			:leave-active-class="inColumn ? '' : 'transition-transform duration-150 ease-in'"
			:leave-to-class="inColumn ? '' : 'translate-x-full'"
		>
			<aside
				v-if="open"
				class="flex flex-col bg-surface-white"
				:class="inColumn ? 'h-full w-full' : 'fixed inset-y-0 right-0 z-40 w-full shadow-2xl lg:w-[768px]'"
				:aria-label="__('Chat about {0}', [title])"
				@keydown.escape="close"
			>
				<header class="flex h-12 flex-shrink-0 items-center gap-2 border-b border-outline-gray-2 px-3">
					<FeatherIcon name="message-circle" class="h-4 w-4 flex-shrink-0 text-ink-gray-6" />
					<span class="min-w-0 flex-1 truncate text-sm font-medium text-ink-gray-9">{{ title }}</span>
					<Button
						variant="ghost"
						:label="__('Open in Raven')"
						:title="__('Open this chat in Raven, in a new window')"
						@click="openInRaven"
					>
						<template #prefix><FeatherIcon name="external-link" class="h-3.5 w-3.5" /></template>
					</Button>
					<Button variant="ghost" :title="__('Close the chat')" :aria-label="__('Close the chat')" @click="close">
						<FeatherIcon name="x" class="h-4 w-4" />
					</Button>
				</header>
				<p
					v-if="skippedUsers.length"
					class="flex-shrink-0 border-b border-outline-gray-2 bg-surface-amber-1 px-3 py-1.5 text-xs text-ink-amber-3"
				>
					{{ __("Not in the chat, since they have no Raven account: {0}", [skippedUsers.map((u) => u.full_name || u.user).join(", ")]) }}
				</p>
				<iframe
					:key="url"
					ref="frame"
					:src="url"
					:title="__('Chat about {0}', [title])"
					class="min-h-0 w-full flex-1 border-0"
					@load="onFrameLoad"
				/>
			</aside>
		</Transition>
	</Teleport>
</template>

<script setup>
// The chat of one record (#1615): its Raven channel in a frame, kept to that channel by
// utils/ravenEmbed.js. From lg on it is a 768px column of the Issue view, the narrowest width at
// which Raven keeps its desktop layout with mouse actions (#1613); IssuesInbox makes room by
// stacking the checklists under the description. Below lg it covers the page. No side border:
// it would take a pixel from the frame and tip Raven into its mobile layout.
import { onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { Button, FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import { injectEmbedStyle, installGuard } from "@spa/utils/ravenEmbed.js"
import { issueChatStore } from "@spa/issueChatStore.js"

const props = defineProps({
	open: { type: Boolean, default: false },
	url: { type: String, required: true },
	title: { type: String, default: "" },
	skippedUsers: { type: Array, default: () => [] },
	/** The record the chat belongs to; IssuesInbox shows the chat column for it */
	recordName: { type: String, default: "" },
})
const emit = defineEmits(["update:open", "closed"])

const router = useRouter()
const frame = ref(null)
let removeGuard = null

// Column on lg screens when the view offers one (Tailwind's lg breakpoint).
const wide = typeof window !== "undefined" ? window.matchMedia("(min-width: 1024px)") : null
const inColumn = ref(false)
function updatePlacement() {
	inColumn.value = Boolean(wide?.matches && document.getElementById("issue-chat-host"))
}
updatePlacement()
onMounted(() => {
	updatePlacement()
	wide?.addEventListener("change", updatePlacement)
})

watch(
	() => props.open,
	(open) => {
		updatePlacement()
		issueChatStore.openFor = open ? props.recordName : null
	},
	{ immediate: true }
)

function close() {
	emit("update:open", false)
	emit("closed")
}

function openInRaven() {
	window.open(frame.value?.contentWindow?.location?.href || props.url, "_blank", "noopener")
}

function onLeave(kind, href) {
	if (kind === "home") return close()
	if (kind === "raven") return void window.open(href, "_blank", "noopener")
	// A link to another page of this site, e.g. a document card: open it here in the cockpit
	// when it belongs to this cockpit, otherwise in a new tab.
	const url = new URL(href)
	const base = router.options.history.base || ""
	if (base && url.pathname.startsWith(base)) {
		close()
		router.push(url.pathname.slice(base.length) + url.search + url.hash)
	} else {
		window.open(href, "_blank", "noopener")
	}
}

function onFrameLoad() {
	removeGuard?.()
	removeGuard = null
	const win = frame.value?.contentWindow
	let doc
	try {
		doc = win?.document
	} catch (e) {
		return // not same-origin; nothing to adjust
	}
	if (!doc) return
	injectEmbedStyle(doc)
	removeGuard = installGuard(win, new URL(props.url, window.location.href).pathname, onLeave)
}

onBeforeUnmount(() => {
	removeGuard?.()
	wide?.removeEventListener("change", updatePlacement)
	if (issueChatStore.openFor === props.recordName) issueChatStore.openFor = null
})
</script>
