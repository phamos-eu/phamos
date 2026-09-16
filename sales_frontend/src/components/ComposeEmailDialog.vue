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
				<FormControl
					v-if="templateOptions.length > 1"
					v-model="selectedTemplate"
					label="Template"
					type="select"
					size="sm"
					:options="templateOptions"
					@change="applyTemplate"
				/>

				<FormControl v-model="recipients" label="To" type="text" size="sm" placeholder="name@example.com" />

				<!-- Addresses already connected to this lead, so the common case
				     is a click rather than typing an address from memory. -->
				<div v-if="availableSuggestions.length" class="flex flex-wrap items-center gap-1.5">
					<button
						v-for="suggestion in availableSuggestions"
						:key="suggestion.email"
						type="button"
						class="rounded-full border border-dashed border-outline-gray-3 px-2 py-0.5 text-xs text-ink-gray-8 hover:border-outline-gray-4 hover:bg-surface-gray-2"
						:title="`${suggestion.email} · ${suggestion.source}`"
						@click="addRecipient(suggestion.email)"
					>
						+ {{ suggestion.label }}
					</button>
				</div>

				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Add an existing contact</label>
					<FrappeLink
						doctype="Contact"
						:model-value="''"
						placeholder="Search contacts…"
						@update:model-value="addContact"
					/>
				</div>
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
import FrappeLink from "@spa/components/FrappeLink.vue"

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
const suggestions = ref([])
const templates = ref([])
const selectedTemplate = ref("")

const templateOptions = computed(() => [
	{ label: "No template", value: "" },
	...templates.value.map((t) => ({ label: t.name, value: t.name })),
])

/** Don't suggest addresses already in one of the fields. */
const availableSuggestions = computed(() => {
	const used = new Set(
		[recipients.value, cc.value, bcc.value]
			.join(",")
			.split(",")
			.map((a) => a.trim().toLowerCase())
			.filter(Boolean)
	)
	return suggestions.value.filter((s) => !used.has(s.email.toLowerCase()))
})

function addRecipient(email) {
	const current = recipients.value.trim()
	recipients.value = current ? `${current}, ${email}` : email
}

async function addContact(contact) {
	if (!contact) return
	try {
		const result = await call("phamos.api.sales_leads.get_contact_emails", { contact })
		if (!result.emails?.length) {
			error.value = `${result.label} has no email address.`
			return
		}
		result.emails.forEach(addRecipient)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load that contact"
	}
}

async function applyTemplate() {
	if (!selectedTemplate.value) return
	try {
		const rendered = await call("phamos.api.sales_leads.render_lead_email_template", {
			lead: props.lead.name,
			template: selectedTemplate.value,
		})
		// Templates carry their own subject; keep a subject the user already
		// typed (a reply's Re: line) rather than overwriting it.
		if (rendered.subject && !subject.value.trim()) subject.value = rendered.subject
		content.value = rendered.message || ""
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load that template"
	}
}

async function loadContext() {
	try {
		const context = await call("phamos.api.sales_leads.get_lead_email_context", {
			lead: props.lead.name,
		})
		suggestions.value = context.suggestions || []
		templates.value = context.templates || []
	} catch (e) {
		suggestions.value = []
		templates.value = []
	}
}

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
		selectedTemplate.value = ""
		loadContext()

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
