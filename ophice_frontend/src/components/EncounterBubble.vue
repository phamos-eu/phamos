<template>
	<!-- The encounter chat of two chips that met (#2056), above (or below) the two of them; the
	     parent places it through the style attribute. -->
	<div
		class="encounter-bubble absolute z-20 flex flex-col rounded-xl border border-outline-gray-2 bg-surface-white text-ink-gray-9 shadow-xl"
		role="dialog"
		:aria-label="__('Chat with {0}', [peer.full_name])"
		:class="inCall ? (movable ? 'cursor-move select-none' : 'w-[67rem]') : 'w-72'"
		data-testid="encounter-bubble"
		@keydown.stop
		@keydown.escape.prevent="emit('close')"
		@pointerdown="onBubbleDown"
	>
		<!-- The top bar, with and without the call (#2135; the call's right bar of #2108 is gone): who,
		     own window, and "Esc to close" as a button that teaches the key. -->
		<header class="flex h-9 flex-shrink-0 items-center gap-2 border-b border-outline-gray-2 px-3" data-testid="bubble-bar">
			<UserAvatar :name="peer.user" :label="peer.full_name" :image="peer.user_image" size="xs" />
			<span class="min-w-0 flex-1 truncate text-sm font-medium">{{ peer.full_name }}</span>
			<!-- The call can move into its own Jitsi window (#2108): bigger, and no cap when the
			     host limits embedded calls. Here it then leaves, so nobody is in it twice. -->
			<button
				v-if="video"
				type="button"
				class="flex flex-shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ink-gray-7 hover:bg-surface-gray-2 hover:text-ink-gray-9 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
				:title="__('Open the video call with {0} in its own window', [firstName])"
				data-testid="open-call"
				@click="emit('call')"
			>
				<PopOutIcon class="h-3.5 w-3.5" />
				{{ inWindow ? __("Call window") : __("Own window") }}
			</button>
			<button
				type="button"
				class="flex flex-shrink-0 items-center gap-1.5 rounded border border-outline-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-7 hover:bg-surface-gray-2 hover:text-ink-gray-9 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
				:title="__('Close the chat and walk on (Esc)')"
				data-testid="close-bubble"
				@click="emit('close')"
			>
				<kbd class="rounded bg-surface-gray-2 px-1 font-sans text-[10px] font-semibold text-ink-gray-7">Esc</kbd>
				{{ __("to close") }}
			</button>
		</header>

		<!-- With the call (#2108): the chat on the left (it takes what the video leaves), the video on
		     the right in the width the parent works out. -->
		<div class="flex min-h-0" :class="inCall ? 'flex-1 flex-row' : 'flex-col'">
			<div class="relative flex min-h-0 flex-col" :class="inCall ? 'min-w-0 flex-1 border-r border-outline-gray-2' : ''">
				<!-- The line between chat and video (#2135): drag it, or arrow keys when focused. The
				     video gets no narrower than 1:1; the parent keeps the width. -->
				<div
					v-if="inCall && movable"
					class="absolute -right-1.5 bottom-0 top-0 z-10 w-3 cursor-ew-resize focus:outline-none focus-visible:bg-outline-gray-3"
					role="separator"
					aria-orientation="vertical"
					tabindex="0"
					:aria-label="__('Width of the chat (arrow keys)')"
					:title="__('Drag to make the chat wider or narrower, or use the arrow keys')"
					data-no-drag
					data-testid="call-split"
					@pointerdown.stop="emit('resize-start', $event, 'split')"
					@keydown.left.prevent="emit('split-by', -SPLIT_STEP)"
					@keydown.right.prevent="emit('split-by', SPLIT_STEP)"
				/>
				<!-- Both chips, as in a meeting area's huddle (#2067). -->
				<MeetingHuddle
					v-if="inCall && meChip"
					class="m-2 mb-0 justify-center"
					compact
					:area="huddleArea"
					:people="[meChip, peer]"
					:me="me"
				/>
				<div
					ref="list"
					class="min-h-[3rem] space-y-1.5 overflow-y-auto px-3 py-2 text-sm"
					:class="inCall ? 'flex-1' : 'max-h-48'"
				>
					<p v-if="loading" class="text-ink-gray-5">
						{{ __("Opening the chat…") }}
					</p>
					<p v-else-if="error" class="text-ink-red-4">{{ error }}</p>
					<p v-else-if="!messages.length" class="text-ink-gray-5">
						{{ __("Say hello to {0}.", [firstName]) }}
					</p>
					<div
						v-for="message in messages"
						:key="message.name"
						class="flex"
						:class="message.owner === me ? 'justify-end' : 'justify-start'"
					>
						<span
							class="max-w-[85%] whitespace-pre-wrap break-words rounded-lg px-2.5 py-1.5"
							:class="message.owner === me ? 'bg-surface-gray-4' : 'bg-surface-gray-2'"
							>{{ message.text }}</span
						>
					</div>
				</div>

				<form v-if="!error && !loading" class="border-t border-outline-gray-2 p-2" @submit.prevent="send">
					<input
						ref="input"
						v-model="draft"
						type="text"
						class="w-full rounded-md border-0 bg-surface-gray-2 px-2.5 py-1.5 text-sm text-ink-gray-9 placeholder-ink-gray-5 focus:ring-2 focus:ring-outline-gray-3"
						:placeholder="__('Write to {0}, Enter to send', [firstName])"
						:maxlength="2000"
						:aria-busy="sending || undefined"
						@keydown="onInputKeydown"
						@focus="chatActive = true"
					/>
				</form>
			</div>

			<!-- The call goes with the nearest person only (#2059); the chat keeps the keyboard. -->
			<!-- Smooth edges (#2108): the video sits inset, with round corners. -->
			<div
				v-if="inCall"
				class="flex-shrink-0 p-2"
				:style="videoWidth ? { width: `${videoWidth + 16}px` } : { width: '48rem' }"
			>
				<VideoCall
					class="h-full rounded-lg"
					fill
					:class="{ 'pointer-events-none': dragging }"
					:domain="video.domain"
					:room="video.room"
					:display-name="displayName"
					@joined="keepChatFocus"
					@stolen="keepChatFocus"
					@toggled="input?.focus()"
				/>
			</div>

		</div>
		<!-- Resize by every edge and corner (#2108); the parent keeps the size. -->
		<template v-if="movable">
			<div
				v-for="handle in RESIZE_HANDLES"
				:key="handle.kind"
				class="absolute z-10"
				:class="handle.class"
				:title="__('Drag to resize')"
				:data-testid="`call-resize-${handle.kind}`"
				@pointerdown.stop="emit('resize-start', $event, handle.kind)"
			/>
			<svg
				viewBox="0 0 16 16"
				class="pointer-events-none absolute bottom-0.5 right-0.5 z-10 h-3.5 w-3.5 text-ink-gray-5"
				aria-hidden="true"
			>
				<path d="M14 6 6 14M14 10l-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none" />
			</svg>
		</template>
	</div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue"
import UserAvatar from "@spa/components/UserAvatar.vue"
import VideoCall from "./VideoCall.vue"
import MeetingHuddle from "./MeetingHuddle.vue"
import PopOutIcon from "./PopOutIcon.vue"
import { ringHue } from "../utils/ophiceColor.js"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	/** The other chip: { user, full_name, user_image } */
	peer: { type: Object, required: true },
	/** Session user, to tell my messages from theirs */
	me: { type: String, required: true },
	messages: { type: Array, default: () => [] },
	loading: { type: Boolean, default: false },
	error: { type: String, default: "" },
	sending: { type: Boolean, default: false },
	/** { domain, room } of the call, or null */
	video: { type: Object, default: null },
	/** My name in the call */
	displayName: { type: String, default: "" },
	/** The call runs in its own window (#2108): no embedded call here. */
	inWindow: { type: Boolean, default: false },
	/** Moved by a press anywhere on it (with the call, #2108). */
	movable: { type: Boolean, default: false },
	/** My chip for the huddle: { user, full_name, user_image } */
	meChip: { type: Object, default: null },
	/** A drag is on: the call's frame must not take the pointer. */
	dragging: { type: Boolean, default: false },
	/** The video's width in px (with the call; the parent keeps 16:9 to 1:1). */
	videoWidth: { type: Number, default: 0 },
})
const emit = defineEmits(["send", "close", "call", "move-start", "resize-start", "split-by"])
// One arrow key press on the line between chat and video, in px.
const SPLIT_STEP = 24

// Edges 8px, corners 16px, a little outside the rounded border so they are easy to hit.
const RESIZE_HANDLES = [
	{ kind: "n", class: "-top-1 left-3 right-3 h-2 cursor-ns-resize" },
	{ kind: "s", class: "-bottom-1 left-3 right-3 h-2 cursor-ns-resize" },
	{ kind: "w", class: "-left-1 top-3 bottom-3 w-2 cursor-ew-resize" },
	{ kind: "e", class: "-right-1 top-3 bottom-3 w-2 cursor-ew-resize" },
	{ kind: "nw", class: "-left-1 -top-1 h-4 w-4 cursor-nwse-resize" },
	{ kind: "ne", class: "-right-1 -top-1 h-4 w-4 cursor-nesw-resize" },
	{ kind: "sw", class: "-bottom-1 -left-1 h-4 w-4 cursor-nesw-resize" },
	{ kind: "se", class: "-bottom-1 -right-1 h-4 w-4 cursor-nwse-resize" },
]

// A press anywhere moves it, except on what is there to click or type into.
function onBubbleDown(event) {
	if (!props.movable || event.target.closest("button, a, input, textarea, select, [data-no-drag]")) return
	emit("move-start", event)
}
// The huddle's tint: the other person's colour.
const huddleArea = computed(() => ({ title: props.peer.full_name, color_hue: ringHue(props.peer.user) }))

const draft = ref("")
const list = ref(null)
const input = ref(null)
// The call shows here unless it moved into its own window.
const inCall = computed(() => !!props.video && !props.inWindow)
const firstName = computed(() => (props.peer.full_name || "").split(" ")[0] || props.peer.full_name)

// Never disabled while sending: a disabled field drops the focus, and the next message should
// follow with just Enter again. send() ignores Enter until the last message went out.

// The chat takes the focus while the user may still hold a movement key: its repeats must not
// type "dddd" into the empty field.
function onInputKeydown(event) {
	if (event.repeat && !draft.value) event.preventDefault()
}

function send() {
	const text = draft.value.trim()
	if (!text || props.sending) return
	emit("send", text, () => (draft.value = ""))
}

// Newest message in view.
watch(
	() => props.messages.length,
	async () => {
		await nextTick()
		if (list.value) list.value.scrollTop = list.value.scrollHeight
	},
	{ immediate: true },
)

// Jitsi's frame may take the focus by itself (on load, on join). Give it back: to the chat if
// the user was in it, otherwise to Ophice, so the keys move the chip again.
const chatActive = ref(false)
function keepChatFocus() {
	if (document.activeElement?.tagName !== "IFRAME") return
	if (chatActive.value) input.value?.focus()
	else {
		document.activeElement.blur()
		window.focus()
	}
}

defineExpose({
	focus: () => input.value?.focus(),
	/** The key that started the chat becomes its first character. */
	insert: (text) => {
		draft.value += text
		input.value?.focus()
	},
})
</script>
