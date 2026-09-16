<template>
	<Dialog
		:options="{
			title: dialogTitle,
			size: '5xl',
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
			<div class="space-y-2.5">
				<!-- Recipients side by side rather than stacked: the header costs
				     one row instead of three, leaving the editor room to breathe.
				     Each field carries its own chip row underneath, so a chip is
				     always right where the address it fills is. -->
				<div class="grid grid-cols-3 gap-3">
					<div v-for="field in recipientFields" :key="field.key">
						<EmailRecipientInput
							:model-value="fields[field.key].value"
							:label="field.label"
							:placeholder="field.placeholder"
							:lead="lead.name"
							@update:model-value="fields[field.key].value = $event"
							@focus="focusedField = field.key"
							@blur="onFieldBlur(field.key)"
						/>
						<!-- Only while this field has focus, so it's clear where a chip
						     lands — but the row keeps its height either way, so the
						     dialog doesn't jump as focus moves. -->
						<div
							class="mt-1.5 flex h-6 items-center gap-1.5 overflow-x-auto whitespace-nowrap"
							:class="focusedField === field.key && availableSuggestions.length ? '' : 'invisible'"
						>
							<template v-if="focusedField === field.key">
								<button
									v-for="suggestion in availableSuggestions"
									:key="suggestion.email"
									type="button"
									class="flex-none rounded-full border border-dashed border-outline-gray-3 px-2 py-0.5 text-xs text-ink-gray-8 hover:border-outline-gray-4 hover:bg-surface-gray-2"
									:title="`${suggestion.email} · ${suggestion.source}`"
									@mousedown.prevent="addRecipient(suggestion.email)"
								>
									+ {{ suggestion.label }}
								</button>
							</template>
						</div>
					</div>
				</div>

				<div class="grid gap-3" :class="templateOptions.length > 1 ? 'grid-cols-3' : 'grid-cols-1'">
					<FormControl
						v-model="subject"
						label="Subject"
						type="text"
						size="sm"
						:class="templateOptions.length > 1 ? 'col-span-2' : ''"
					/>
					<FormControl
						v-if="templateOptions.length > 1"
						v-model="selectedTemplate"
						label="Template"
						type="select"
						size="sm"
						:options="templateOptions"
						@change="applyTemplate"
					/>
				</div>

				<div>
					<TextEditor
						v-if="modelValue"
						:content="content"
						:fixed-menu="editorMenu"
						placeholder="Write your message…"
						editor-class="prose-sm dark:prose-invert max-w-none w-full min-h-[200px] max-h-[40vh] overflow-y-auto px-3 py-2 border border-t-0 border-outline-gray-2 rounded-b-lg bg-surface-white"
						@change="(html) => (content = html)"
					/>
				</div>

				<!-- The footer is assembled by the system at send time (Email Account
				     footer, System Settings' address, the standard footer), so it
				     can't be edited here — but it does go out, so show it. -->
				<details v-if="footer" class="rounded border border-outline-gray-2 bg-surface-gray-1 px-2.5 py-1.5">
					<summary class="cursor-pointer select-none text-xs text-ink-gray-5">
						Footer added when sent
					</summary>
					<div
						class="mt-1.5 max-h-24 overflow-y-auto border-t border-outline-gray-2 pt-1.5 text-xs text-ink-gray-6 [&_a]:underline"
						v-html="footer"
					/>
				</details>

				<div class="flex flex-wrap items-center gap-1.5">
					<FileUploader
						:upload-args="{
							doctype: 'Lead',
							docname: lead.name,
							private: 1,
							folder: 'Home/Attachments',
						}"
						@success="onFileUploaded"
						@failure="onFileFailed"
					>
						<template #default="{ openFileSelector, uploading, progress }">
							<Button
								size="sm"
								variant="subtle"
								:loading="uploading"
								:label="uploading ? `Uploading ${progress}%` : 'Attach file'"
								@click="openFileSelector"
							>
								<template #prefix><FeatherIcon name="paperclip" class="h-3.5 w-3.5" /></template>
							</Button>
						</template>
					</FileUploader>

					<span
						v-for="file in attachments"
						:key="file.name"
						class="inline-flex max-w-[14rem] items-center gap-1 rounded-full bg-surface-gray-3 py-0.5 pl-2 pr-1 text-xs text-ink-gray-9"
					>
						<span class="truncate">{{ file.file_name }}</span>
						<button
							type="button"
							class="rounded-full p-0.5 text-ink-gray-6 hover:bg-surface-gray-4 hover:text-ink-gray-9"
							:title="`Remove ${file.file_name}`"
							@click="removeAttachment(file)"
						>
							<FeatherIcon name="x" class="h-3 w-3" />
						</button>
					</span>

					<span class="ml-auto text-xs text-ink-gray-5">
						Sent from the system and filed against this lead, so replies stay linked.
					</span>
				</div>
				<ErrorMessage :message="error" />
			</div>
		</template>
	</Dialog>
</template>

<script>
/** Module scope, so drafts survive the dialog being torn down and rebuilt —
 *  and are shared by every instance across the cockpit, like Desk's
 *  `frappe.last_edited_communication`. Session-lived: a page reload clears them. */
const drafts = new Map()
</script>

<script setup>
import { computed, ref, watch } from "vue"
import { call, FileUploader, TextEditor } from "frappe-ui"
import EmailRecipientInput from "@/components/EmailRecipientInput.vue"

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

const recipientFields = [
	{ key: "recipients", label: "To", placeholder: "name@example.com" },
	{ key: "cc", label: "Cc", placeholder: "" },
	{ key: "bcc", label: "Bcc", placeholder: "" },
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
const attachments = ref([])
const signature = ref("")
const footer = ref("")
/** Which recipient field the chips currently add to. */
const focusedField = ref("")

const fields = { recipients, cc, bcc }

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
	const field = fields[focusedField.value] || recipients
	const current = field.value.trim().replace(/,$/, "").trim()
	field.value = current ? `${current}, ${email}` : email
}

/** Chips use mousedown.prevent so they never blur the field; a real blur
 *  (tabbing away, clicking the editor) should hide them. Moving between two
 *  recipient fields fires the next focus first, so only clear if this field
 *  is still the focused one. */
function onFieldBlur(field) {
	setTimeout(() => {
		if (focusedField.value === field) focusedField.value = ""
	}, 120)
}

function onFileUploaded(file) {
	if (!file?.name) return
	attachments.value = [
		...attachments.value,
		{ name: file.name, file_name: file.file_name || file.file_url },
	]
}

function onFileFailed(e) {
	error.value = e?.messages?.[0] || e?.message || "Could not upload that file"
}

async function removeAttachment(file) {
	attachments.value = attachments.value.filter((f) => f.name !== file.name)
	try {
		await call("phamos.api.sales_leads.remove_lead_attachment", {
			lead: props.lead.name,
			file: file.name,
		})
	} catch (e) {
		// The file is off the email either way; a leftover File row on the lead
		// isn't worth blocking the user with.
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
		content.value = withSignature(rendered.message || "")
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
		signature.value = context.signature || ""
		footer.value = context.footer || ""
	} catch (e) {
		suggestions.value = []
		templates.value = []
		signature.value = ""
		footer.value = ""
	}
}

/** The signature is part of the body — editable, and shown where it'll land.
 *  (The footer isn't: the system adds it at send time, so it's a preview.) */
function withSignature(html) {
	const sig = signature.value
	if (!sig || (html || "").includes(sig)) return html || ""
	return `${html || ""}<p><br></p>${sig}`
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

/** What the dialog starts from when there's nothing half-written to restore. */
function defaultValues() {
	const source = props.source
	if (props.mode === "reply" && source) {
		return {
			recipients: source.sender || props.lead.email_id || "",
			subject: threadSubject(source.subject, "Re"),
			content: "",
		}
	}
	if (props.mode === "forward" && source) {
		return {
			// Forwarding is the user choosing someone new, so leave To empty.
			recipients: "",
			subject: threadSubject(source.subject, "Fwd"),
			content: `<p><br></p><hr><p>From: ${source.sender || ""}<br>Subject: ${
				source.subject || ""
			}</p>${source.content || ""}`,
		}
	}
	return { recipients: props.lead.email_id || "", subject: "", content: "" }
}

/** One draft per lead + what's being written, so a half-typed reply doesn't
 *  reappear inside a new email. Held in memory for the session, matching how
 *  Desk's own composer keeps its last edited communication. */
function draftKey() {
	return [props.lead.name, props.mode, props.source?.name || ""].join("|")
}

function stashDraft() {
	const defaults = defaultValues()
	const untouched =
		content.value === withSignature(defaults.content) &&
		!attachments.value.length &&
		!cc.value.trim() &&
		!bcc.value.trim() &&
		recipients.value === defaults.recipients &&
		subject.value === defaults.subject
	if (untouched) {
		drafts.delete(draftKey())
		return
	}
	drafts.set(draftKey(), {
		recipients: recipients.value,
		cc: cc.value,
		bcc: bcc.value,
		subject: subject.value,
		content: content.value,
		attachments: [...attachments.value],
		selectedTemplate: selectedTemplate.value,
	})
}

function restore(values) {
	recipients.value = values.recipients ?? ""
	cc.value = values.cc ?? ""
	bcc.value = values.bcc ?? ""
	subject.value = values.subject ?? ""
	content.value = values.content ?? ""
	attachments.value = values.attachments ? [...values.attachments] : []
	selectedTemplate.value = values.selectedTemplate ?? ""
}

watch(
	() => props.modelValue,
	(open) => {
		if (!open) {
			// Closing is "not now", not "discard" — pick the message back up on reopen.
			stashDraft()
			return
		}
		error.value = ""
		focusedField.value = ""

		const draft = drafts.get(draftKey())
		restore(draft || defaultValues())
		loadContext().then(() => {
			// A draft already carries whatever the user did with the signature.
			if (!draft) content.value = withSignature(content.value)
		})
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
			recipients: recipients.value.trim().replace(/,$/, ""),
			cc: cc.value.trim().replace(/,$/, "") || null,
			bcc: bcc.value.trim().replace(/,$/, "") || null,
			subject: subject.value.trim(),
			content: content.value,
			attachments: JSON.stringify(attachments.value.map((f) => f.name)),
			// Threads the reply to the original message, not just by subject.
			in_reply_to: props.mode === "reply" ? props.source?.name : null,
		})
		// Sent, so there's nothing left to pick back up. Reset to the defaults
		// the dialog would open with, so closing doesn't stash them back.
		drafts.delete(draftKey())
		restore(defaultValues())
		content.value = withSignature(content.value)
		emit("sent")
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not send the email"
	} finally {
		sending.value = false
	}
}
</script>
