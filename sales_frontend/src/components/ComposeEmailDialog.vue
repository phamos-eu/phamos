<template>
	<Dialog
		:options="{
			title: dialogTitle,
			size: '3xl',
			actions: [
				{ label: 'Cancel', variant: 'subtle', onClick: () => emit('update:modelValue', false) },
				{
					label: sending ? 'Sending…' : 'Send',
					variant: 'solid',
					loading: sending,
					onClick: submit,
				},
			],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-3">
				<FormControl v-model="recipients" label="To" type="text" size="sm" placeholder="name@example.com" />
				<div class="grid grid-cols-2 gap-3">
					<FormControl v-model="cc" label="Cc" type="text" size="sm" />
					<FormControl v-model="bcc" label="Bcc" type="text" size="sm" />
				</div>
				<FormControl v-model="subject" label="Subject" type="text" size="sm" />
				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Message</label>
					<TextEditor
						v-if="modelValue"
						:content="content"
						:fixed-menu="editorMenu"
						placeholder="Write your message…"
						editor-class="prose-sm dark:prose-invert max-w-none w-full min-h-[180px] max-h-[320px] overflow-y-auto px-3 py-2 border border-t-0 border-outline-gray-2 rounded-b-lg bg-surface-white"
						@change="(html) => (content = html)"
					/>
				</div>
				<p class="text-xs text-ink-gray-5">
					Sent from the system and filed against this lead, so replies stay linked.
				</p>
				<ErrorMessage :message="error" />
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call, TextEditor } from "frappe-ui"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	lead: { type: Object, required: true },
	/** "new" | "reply" | "forward" */
	mode: { type: String, default: "new" },
	/** The communication being replied to / forwarded */
	source: { type: Object, default: null },
})

const emit = defineEmits(["update:modelValue", "sent"])

const editorMenu = [
	"Paragraph",
	"Bold",
	"Italic",
	"Link",
	"Separator",
	"Bullet List",
	"Numbered List",
]

const recipients = ref("")
const cc = ref("")
const bcc = ref("")
const subject = ref("")
const content = ref("")
const sending = ref(false)
const error = ref("")

const dialogTitle = computed(() => {
	if (props.mode === "reply") return "Reply"
	if (props.mode === "forward") return "Forward"
	return "New Email"
})

/** Keep the thread's subject rather than stacking Re: on Re:. */
function threadSubject(value, prefix) {
	let clean = (value || "").trim()
	let previous = null
	while (previous !== clean) {
		previous = clean
		clean = clean.replace(/^\s*(re|fwd|fw|aw|wg)\s*:\s*/i, "")
	}
	return prefix ? `${prefix}: ${clean}` : clean
}

watch(
	() => props.modelValue,
	(open) => {
		if (!open) return
		error.value = ""
		cc.value = ""
		bcc.value = ""

		const source = props.source
		if (props.mode === "reply" && source) {
			recipients.value = source.sender || props.lead.email_id || ""
			subject.value = threadSubject(source.subject, "Re")
			content.value = ""
		} else if (props.mode === "forward" && source) {
			// Forwarding is the user choosing someone new, so leave To empty.
			recipients.value = ""
			subject.value = threadSubject(source.subject, "Fwd")
			content.value = `<p><br></p><hr><p>From: ${source.sender || ""}<br>Subject: ${
				source.subject || ""
			}</p>${source.content || ""}`
		} else {
			recipients.value = props.lead.email_id || ""
			subject.value = ""
			content.value = ""
		}
	}
)

async function submit() {
	error.value = ""
	if (!recipients.value.trim()) {
		error.value = "At least one recipient is required."
		return
	}
	if (!subject.value.trim()) {
		error.value = "A subject is required."
		return
	}

	sending.value = true
	try {
		await call("phamos.api.sales_leads.send_lead_email", {
			lead: props.lead.name,
			recipients: recipients.value.trim(),
			cc: cc.value.trim() || null,
			bcc: bcc.value.trim() || null,
			subject: subject.value.trim(),
			content: content.value,
			// Threads the reply to the original message, not just by subject.
			in_reply_to: props.mode === "reply" ? props.source?.name : null,
		})
		emit("sent")
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not send the email"
	} finally {
		sending.value = false
	}
}
</script>
