<template>
	<!--
		The guest chat (#2083): in the guest area and customer meeting areas, for guests and
		employees. Kept only for a short while on the server; "Save by e-mail" opens a draft in the
		person's own mail program, laid out like the chat, with the phamos header and Ophice link.
	-->
	<section
		class="flex min-h-0 flex-col overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-white text-ink-gray-9"
		:aria-label="__('Chat of {0}', [title])"
		data-testid="guest-chat"
	>
		<header class="flex flex-shrink-0 items-center gap-2 border-b border-outline-gray-2 px-3 py-2">
			<FeatherIcon name="message-square" class="h-4 w-4 flex-shrink-0 text-ink-gray-6" />
			<span class="min-w-0 flex-1 truncate text-sm font-medium">{{ title }}</span>
			<button
				type="button"
				class="flex flex-shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9 disabled:opacity-40"
				:disabled="!messages.length"
				:title="__('Opens a draft in your mail program with this chat')"
				data-testid="guest-chat-mail"
				@click="mail"
			>
				<FeatherIcon name="mail" class="h-3.5 w-3.5" />
				{{ __("Save by e-mail") }}
			</button>
			<button
				type="button"
				class="flex-shrink-0 rounded p-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9 disabled:opacity-40"
				:disabled="!messages.length"
				:title="__('Copy the whole chat')"
				data-testid="guest-chat-copy"
				@click="copy"
			>
				<FeatherIcon name="copy" class="h-3.5 w-3.5" />
			</button>
		</header>
		<p class="flex-shrink-0 border-b border-outline-gray-1 bg-surface-gray-1 px-3 py-1 text-xs text-ink-gray-5">
			{{ __("Not stored: this chat is deleted 10 minutes after everyone has left. Save it by e-mail if you need it.") }}
		</p>
		<div ref="list" class="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-2" data-testid="guest-chat-messages">
			<p v-if="!messages.length" class="text-xs text-ink-gray-5">{{ __("No messages yet. Say hello.") }}</p>
			<div
				v-for="message in messages"
				:key="message.name"
				class="flex flex-col"
				:class="message.owner === me ? 'items-end' : 'items-start'"
			>
				<span v-if="message.owner !== me" class="flex items-center gap-1 text-[11px] text-ink-gray-5">
					{{ message.author }}
					<span v-if="message.guest" class="rounded-full bg-amber-600 px-1 text-[9px] font-semibold leading-3 text-white">{{ __("Guest") }}</span>
				</span>
				<span
					class="max-w-[90%] whitespace-pre-wrap break-words rounded-lg px-2.5 py-1.5 text-sm"
					:class="message.owner === me ? 'bg-surface-gray-7 text-ink-white' : 'bg-surface-gray-2'"
				>{{ message.text }}</span>
				<span class="mt-0.5 text-[10px] text-ink-gray-4" :title="clockTime(new Date(message.ts * 1000), new Date(0))">
					{{ ago(message) }}
				</span>
			</div>
		</div>
		<form class="flex flex-shrink-0 items-end gap-2 border-t border-outline-gray-2 p-2" @submit.prevent="send">
			<textarea
				v-model="text"
				rows="1"
				maxlength="1000"
				class="form-textarea min-h-[34px] flex-1 resize-none rounded border-outline-gray-2 bg-surface-gray-2 text-sm text-ink-gray-9"
				:placeholder="__('Write a message')"
				data-testid="guest-chat-input"
				@keydown.enter.exact.prevent="send"
				@keydown.esc.stop.prevent="$event.target.blur()"
			/>
			<Button type="submit" variant="solid" :loading="sending" :disabled="!text.trim()">
				<FeatherIcon name="send" class="h-4 w-4" />
			</Button>
		</form>
		<p v-if="error" class="px-3 pb-2 text-xs text-ink-red-4">{{ error }}</p>
	</section>
</template>

<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from "vue"
import { Button, FeatherIcon, toast } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"
import { clockTime, withinMinutes } from "../utils/ophiceTime.js"

const props = defineProps({
	/** the area's name, shown in the header and the mail subject */
	title: { type: String, default: "" },
	/** [{ name, owner, author, guest, text, ts (epoch seconds) }] */
	messages: { type: Array, default: () => [] },
	/** my owner id: my user, or "guest:<id>" */
	me: { type: String, default: "" },
	/** async (text) => message; throws with a readable message */
	onSend: { type: Function, required: true },
	/** where the Ophice link in the mail points: /ophice (employees) or /ophice/guest (guests) */
	ophicePath: { type: String, default: "/ophice" },
})

const text = ref("")
const sending = ref(false)
const error = ref("")
const list = ref(null)
const now = ref(Date.now())
const ticker = setInterval(() => (now.value = Date.now()), 15000)
onBeforeUnmount(() => clearInterval(ticker))

// Up to 90 minutes "in the last 15/30/… minutes", then the time (as in the area chat, #2066).
function ago(message) {
	const date = new Date(message.ts * 1000)
	const current = new Date(now.value)
	return current - date < 90 * 60000 ? withinMinutes(date, current) : clockTime(date, current)
}

watch(
	() => props.messages.length,
	() => nextTick(() => list.value && (list.value.scrollTop = list.value.scrollHeight)),
	{ immediate: true }
)

async function send() {
	const value = text.value.trim()
	if (!value || sending.value) return
	sending.value = true
	error.value = ""
	try {
		await props.onSend(value)
		text.value = ""
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("The message could not be sent.")
	} finally {
		sending.value = false
	}
}

// --- Saving: a mail draft (plain text, as mailto allows) and the clipboard.

// Mail programs cut long mailto links; the newest messages are kept, "Copy chat" has them all.
const MAIL_BODY_LIMIT = 1800
const RULE = "-".repeat(32)

function lineOf(message) {
	const at = clockTime(new Date(message.ts * 1000), new Date(0))
	const who = message.guest ? `${message.author} (${__("Guest")})` : message.author
	return `[${at}] ${who}: ${message.text}`
}

function footer() {
	return [RULE, `phamos GmbH · Ophice: ${window.location.origin}${props.ophicePath}`]
}

function header() {
	return [`phamos Ophice · ${__("Chat of {0}", [props.title])}`, RULE]
}

function wholeChat() {
	return [...header(), ...props.messages.map(lineOf), ...footer()].join("\n")
}

function mail() {
	const head = header()
	const foot = footer()
	const lines = []
	let size = [...head, ...foot].join("\n").length
	let cut = false
	for (const message of [...props.messages].reverse()) {
		const line = lineOf(message)
		if (size + line.length + 1 > MAIL_BODY_LIMIT) {
			cut = true
			break
		}
		lines.unshift(line)
		size += line.length + 1
	}
	if (cut) lines.unshift(__("(Earlier messages left out: use \"Copy chat\" for all of them.)"))
	const body = [...head, ...lines, ...foot].join("\n")
	const subject = `phamos Ophice · ${props.title}`
	window.location.href = `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
}

async function copy() {
	try {
		await navigator.clipboard.writeText(wholeChat())
		toast({ title: __("Chat copied"), icon: "check" })
	} catch {
		toast({ title: __("The chat could not be copied."), icon: "alert-circle" })
	}
}
</script>
