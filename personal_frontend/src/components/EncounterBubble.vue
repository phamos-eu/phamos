<template>
	<!-- The encounter chat of two chips that met (#2056), above (or below) the two of them; the
	     parent places it through the style attribute. -->
	<div
		class="encounter-bubble absolute z-20 flex w-72 flex-col rounded-xl border border-outline-gray-2 bg-surface-white text-ink-gray-9 shadow-xl"
		role="dialog"
		:aria-label="__('Chat with {0}', [peer.full_name])"
		data-testid="encounter-bubble"
		@keydown.stop
		@keydown.escape.prevent="emit('close')"
	>
		<header class="flex items-center gap-2 border-b border-outline-gray-2 px-3 py-2">
			<UserAvatar :name="peer.user" :label="peer.full_name" :image="peer.user_image" size="xs" />
			<span class="min-w-0 flex-1 truncate text-sm font-medium">{{ peer.full_name }}</span>
			<button
				type="button"
				class="flex-shrink-0 rounded px-1.5 py-0.5 text-xs text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8"
				:title="__('Close the chat and walk on')"
				@click="emit('close')"
			>
				{{ __("Esc to close") }}
			</button>
		</header>

		<div ref="list" class="max-h-48 min-h-[3rem] space-y-1.5 overflow-y-auto px-3 py-2 text-sm">
			<p v-if="loading" class="text-ink-gray-5">{{ __("Opening the chat…") }}</p>
			<p v-else-if="error" class="text-ink-red-4">{{ error }}</p>
			<p v-else-if="!messages.length" class="text-ink-gray-5">{{ __("Say hello to {0}.", [firstName]) }}</p>
			<div
				v-for="message in messages"
				:key="message.name"
				class="flex"
				:class="message.owner === me ? 'justify-end' : 'justify-start'"
			>
				<span
					class="max-w-[85%] whitespace-pre-wrap break-words rounded-lg px-2.5 py-1.5"
					:class="message.owner === me ? 'bg-surface-gray-4' : 'bg-surface-gray-2'"
				>{{ message.text }}</span>
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
			/>
		</form>
	</div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue"
import UserAvatar from "@spa/components/UserAvatar.vue"
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
})
const emit = defineEmits(["send", "close"])

const draft = ref("")
const list = ref(null)
const input = ref(null)
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
	{ immediate: true }
)

defineExpose({ focus: () => input.value?.focus() })
</script>
