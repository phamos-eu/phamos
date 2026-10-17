<template>
	<!-- Wide screens: a permanent column of the Issue view (#issue-chat-host in IssuesInbox).
	     Below lg, or where the view has no such column, it covers the page from the right. -->
	<Teleport :to="inColumn ? '#issue-chat-host' : 'body'">
		<Transition
			:enter-active-class="inColumn ? '' : 'transition-transform duration-200 ease-out'"
			:enter-from-class="inColumn ? '' : 'translate-x-full'"
			:leave-active-class="inColumn ? '' : 'transition-transform duration-150 ease-in'"
			:leave-to-class="inColumn ? '' : 'translate-x-full'"
		>
			<aside
				v-if="shown"
				class="flex flex-col bg-surface-white"
				:class="inColumn ? 'h-full w-full' : 'fixed inset-y-0 right-0 z-40 w-full shadow-2xl lg:w-[768px]'"
				:aria-label="__('Chat about {0}', [title])"
				@keydown.escape="close"
			>
				<header class="flex h-12 flex-shrink-0 items-center gap-2 border-b border-outline-gray-2 px-3">
					<FeatherIcon name="message-circle" class="h-4 w-4 flex-shrink-0 text-ink-gray-6" />
					<span class="min-w-0 flex-1 truncate text-sm font-medium text-ink-gray-9">{{ __("Chat") }}</span>
					<Button
						v-if="url"
						variant="ghost"
						:label="__('Open in Raven')"
						:title="__('Open this chat in Raven, in a new window')"
						@click="openInRaven"
					>
						<template #prefix><FeatherIcon name="external-link" class="h-3.5 w-3.5" /></template>
					</Button>
					<Button
						v-if="!inColumn"
						variant="ghost"
						:title="__('Close the chat')"
						:aria-label="__('Close the chat')"
						@click="close"
					>
						<FeatherIcon name="x" class="h-4 w-4" />
					</Button>
				</header>
				<p
					v-if="skippedUsers.length"
					class="flex-shrink-0 border-b border-outline-gray-2 bg-surface-amber-1 px-3 py-1.5 text-xs text-ink-amber-3"
				>
					{{ __("Not in the chat, since they have no Raven account: {0}", [skippedUsers.map((u) => u.full_name || u.user).join(", ")]) }}
				</p>
				<!-- Replies in threads, which Raven's channel view does not mark (#1623). Drawn like Raven's
				     "New messages" divider, with Raven's red unread badge in the middle. -->
				<div v-if="url && threads.length" class="flex-shrink-0 border-b border-outline-gray-1 px-4 py-2">
					<div class="flex items-center gap-2">
						<span class="h-px flex-1 bg-red-200 dark:bg-red-900" aria-hidden="true" />
						<button
							type="button"
							class="inline-flex h-5 items-center gap-1 rounded-full bg-surface-red-5 px-2 text-xs font-semibold text-ink-white hover:opacity-90"
							:aria-expanded="threads.length > 1 ? String(threadListOpen) : undefined"
							@click="onThreadHint"
						>
							<FeatherIcon name="corner-down-right" class="h-3 w-3 flex-none" />
							{{ threadHint }}
							<FeatherIcon
								v-if="threads.length > 1"
								:name="threadListOpen ? 'chevron-up' : 'chevron-down'"
								class="h-3 w-3 flex-none"
							/>
						</button>
						<span class="h-px flex-1 bg-red-200 dark:bg-red-900" aria-hidden="true" />
					</div>
					<ul v-if="threadListOpen && threads.length > 1" class="mt-2 space-y-0.5">
						<li v-for="thread in threads" :key="thread.thread_id">
							<button
								type="button"
								class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-gray-2"
								@click="openThread(thread.thread_id)"
							>
								<span class="min-w-0 flex-1 truncate font-semibold text-ink-gray-8">{{ thread.preview || __("Thread") }}</span>
								<span v-if="thread.last_sender" class="flex-none truncate text-xs text-ink-gray-5">{{ thread.last_sender }}</span>
								<span class="inline-flex h-4 flex-none items-center rounded-full bg-surface-red-5 px-1.5 text-[10px] font-semibold text-ink-white">
									{{ __("{0} new", [thread.unread]) }}
								</span>
							</button>
						</li>
					</ul>
				</div>
				<iframe
					v-if="frameUrl"
					v-show="url"
					ref="frame"
					:src="frameUrl"
					:title="__('Chat about {0}', [title])"
					class="min-h-0 w-full flex-1 border-0"
					@load="onFrameLoad"
				/>
				<div v-if="!url" class="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
					<slot name="placeholder" />
				</div>
			</aside>
		</Transition>
	</Teleport>
</template>

<script setup>
// The chat of one record (#1615): its Raven channel in a frame, kept to that channel by
// utils/ravenEmbed.js. From lg on it is a permanent 768px column of the Issue view, the narrowest
// width at which Raven keeps its desktop layout with mouse actions (#1613); IssuesInbox makes room
// by stacking the checklists under the description. Without a chat (or before joining it) the
// column shows the `placeholder` slot. Below lg it is an overlay the chat button toggles.
// No side border: it would take a pixel from the frame and tip Raven into its mobile layout.
//
// The frame is loaded once. Moving to another record's chat switches the channel inside the
// running Raven (its router), instead of booting Raven again for every Issue.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { Button, FeatherIcon } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import { injectEmbedStyle, installGuard, watchThreadMarks } from "@spa/utils/ravenEmbed.js"
import { issueChatStore } from "@spa/issueChatStore.js"

const props = defineProps({
	/** Overlay only: whether it is shown. The column is always shown. */
	open: { type: Boolean, default: false },
	/** The channel route; empty while there is no chat to show yet */
	url: { type: String, default: "" },
	title: { type: String, default: "" },
	skippedUsers: { type: Array, default: () => [] },
	/** The record the chat belongs to; IssuesInbox shows the chat column for it */
	recordName: { type: String, default: "" },
	/** Threads with unread replies: [{ thread_id, unread, preview, last_sender }] */
	threads: { type: Array, default: () => [] },
})
const emit = defineEmits(["update:open", "closed", "thread-opened"])

const router = useRouter()
const frame = ref(null)
// What the frame was loaded with; later channel changes happen inside Raven.
const frameUrl = ref(props.url)
let removeGuard = null
let frameReady = false

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

const shown = computed(() => inColumn.value || props.open)

// IssuesInbox shows the chat column (and stacks Description and Checklists) for this record.
watch(
	[() => shown.value && inColumn.value, () => props.recordName],
	([inUse, record], previous) => {
		const before = previous?.[1]
		if (before && before !== record && issueChatStore.openFor === before) issueChatStore.openFor = null
		if (inUse) issueChatStore.openFor = record
		else if (issueChatStore.openFor === record) issueChatStore.openFor = null
	},
	{ immediate: true }
)

function channelPath(url) {
	return url ? new URL(url, window.location.href).pathname : ""
}

watch(
	() => props.url,
	(url) => {
		if (!url) return
		if (!frameUrl.value || !frameReady) {
			frameUrl.value = url
			return
		}
		switchChannel(url)
	}
)

// Point the running Raven at another channel: move its history and let its router follow.
function switchChannel(url) {
	const win = frame.value?.contentWindow
	try {
		removeGuard?.()
		removeGuard = null
		win.History.prototype.pushState.call(win.history, null, "", channelPath(url))
		win.dispatchEvent(new win.PopStateEvent("popstate", { state: null }))
		removeGuard = installGuard(win, channelPath(url), onLeave, onThreadOpened)
	} catch (e) {
		frameReady = false
		frameUrl.value = url // fall back to loading it
	}
}

// Thread pills with new replies get a mark inside the frame (#1623).
let threadMarks = null
const threadLabels = computed(() =>
	Object.fromEntries(props.threads.map((t) => [t.thread_id, __("{0} new", [t.unread])]))
)
watch(threadLabels, () => threadMarks?.refresh())

function startThreadMarks(doc) {
	threadMarks?.stop()
	threadMarks = doc?.body ? watchThreadMarks(doc, () => threadLabels.value) : null
}

const threadListOpen = ref(false)
const threadReplies = computed(() => props.threads.reduce((sum, t) => sum + (t.unread || 0), 0))
const threadHint = computed(() =>
	threadReplies.value === 1
		? __("1 new reply in threads")
		: __("{0} new replies in threads", [threadReplies.value])
)
watch(
	() => props.threads.length,
	(count) => {
		if (count < 2) threadListOpen.value = false
	}
)

function onThreadHint() {
	if (props.threads.length === 1) openThread(props.threads[0].thread_id)
	else threadListOpen.value = !threadListOpen.value
}

// Open a thread of this chat inside the frame: a route Raven knows and the guard allows, so its
// router opens the thread panel, which marks the thread read.
function openThread(threadId) {
	const win = frame.value?.contentWindow
	if (!win || !props.url) return
	try {
		win.history.pushState(null, "", `${channelPath(props.url)}/thread/${encodeURIComponent(threadId)}`)
		win.dispatchEvent(new win.PopStateEvent("popstate", { state: null }))
	} catch (e) {
		return
	}
	threadListOpen.value = false
}

// A thread of this chat opened in the frame, from the hint or Raven's own pill.
function onThreadOpened(threadId) {
	emit("thread-opened", threadId)
}

function close() {
	if (inColumn.value) return
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
	startThreadMarks(doc)
	frameReady = true
	if (props.url && channelPath(props.url) !== channelPath(frameUrl.value)) {
		// The record changed while Raven was still loading.
		switchChannel(props.url)
		return
	}
	removeGuard = installGuard(win, channelPath(frameUrl.value), onLeave, onThreadOpened)
	if (pendingTarget) {
		const target = pendingTarget
		pendingTarget = null
		focusTarget(target)
	}
}

// Where the chat should land once Raven is ready (set before the frame finished loading).
let pendingTarget = null

function targetPath(target) {
	let path = channelPath(props.url)
	if (target?.threadId) path += `/thread/${encodeURIComponent(target.threadId)}`
	if (target?.messageId) path += `?message_id=${encodeURIComponent(target.messageId)}`
	return path
}

/**
 * Go to a message or thread of this chat: { messageId, threadId }. Raven's `?message_id=`
 * scrolls to the message and highlights it; a thread opens in its panel.
 */
function focusTarget(target) {
	if (!target || (!target.messageId && !target.threadId) || !props.url) return
	const win = frame.value?.contentWindow
	if (!frameReady || !win) {
		pendingTarget = target
		return
	}
	try {
		win.history.pushState(null, "", targetPath(target))
		win.dispatchEvent(new win.PopStateEvent("popstate", { state: null }))
	} catch (e) {
		// The chat still shows; only the jump is lost.
	}
}

defineExpose({ focusTarget, inColumn })

onBeforeUnmount(() => {
	removeGuard?.()
	threadMarks?.stop()
	wide?.removeEventListener("change", updatePlacement)
	if (issueChatStore.openFor === props.recordName) issueChatStore.openFor = null
})
</script>
