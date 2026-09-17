<template>
	<Dialog
		:options="{
			title: dialogTitle,
			size: '7xl',
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
			<!-- Two columns, not a calendar tucked inside the message: picking a
			     time and writing the mail are separate jobs done side by side. -->
			<div class="grid grid-cols-[minmax(0,1fr)_22rem] gap-4">
				<div class="space-y-2.5">
				<!-- Recipients side by side rather than stacked: the header costs
				     one row instead of three, leaving the editor room to breathe. -->
				<div class="grid grid-cols-3 gap-3">
					<EmailRecipientInput
						v-for="field in recipientFields"
						:key="field.key"
						:model-value="fields[field.key].value"
						:label="field.label"
						:placeholder="field.placeholder"
						:lead="lead.name"
						@update:model-value="fields[field.key].value = $event"
						@focus="focusedField = field.key"
						@blur="onFieldBlur(field.key)"
					/>
				</div>

				<!-- One row across all three fields rather than one per column:
				     an address needs the width to be readable, and a column's
				     worth of it hid most of them. Which field a chip lands in is
				     said in words, since position no longer says it. The row
				     keeps its height either way so the dialog doesn't jump. -->
				<!-- Fixed height, not a minimum: the number of suggestions varies per
				     lead and per focused field, and the dialog must not resize under
				     the user because of it. Overflow scrolls inside. -->
				<div
					class="h-[4.5rem] overflow-hidden rounded border border-outline-gray-2 bg-surface-gray-1 px-2 py-1.5"
					:class="chipsVisible ? '' : 'invisible'"
				>
					<template v-if="chipsVisible">
						<!-- No heading: the space buys a second row of addresses, and the
						     field a chip lands in is the one the cursor is already in. -->
						<div class="flex h-full flex-wrap content-start gap-1.5 overflow-y-auto">
							<button
								v-for="suggestion in availableSuggestions"
								:key="suggestion.email"
								type="button"
								class="flex max-w-full items-baseline gap-1.5 rounded-full border border-dashed border-outline-gray-3 px-2 py-0.5 text-xs hover:border-outline-gray-4 hover:bg-surface-gray-2"
								:title="`Add to ${focusedLabel} · ${suggestion.source}`"
								@mousedown.prevent="addRecipient(suggestion.email)"
							>
								<span class="flex-none text-ink-gray-8">{{ suggestion.label }}</span>
								<span
									v-if="suggestion.label !== suggestion.email"
									class="min-w-0 truncate text-ink-gray-5"
								>
									{{ suggestion.email }}
								</span>
							</button>
						</div>
					</template>
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

				<!-- Slots picked from the calendar, ready to drop into the message. -->
				<div v-if="pickedSlots.length" class="flex flex-wrap items-center gap-1.5">
					<span class="text-xs text-ink-gray-5">Suggested times:</span>
					<button
						v-for="slot in pickedSlots"
						:key="slot.starts_on"
						type="button"
						class="flex items-center gap-1 rounded-full bg-surface-green-2 px-2 py-0.5 text-xs text-ink-green-3 hover:bg-surface-green-3"
						title="Add to the message"
						@click="insertSlot(slot)"
					>
						<span>{{ slotLabel(slot) }}</span>
						<FeatherIcon name="corner-down-left" class="h-3 w-3" />
					</button>
					<button
						type="button"
						class="rounded px-1.5 py-0.5 text-xs text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
						@click="insertAllSlots"
					>
						Add all
					</button>
				</div>

				<TextEditor
					v-if="modelValue"
					:content="content"
					:fixed-menu="editorMenu"
					placeholder="Write your message…"
					editor-class="prose-sm dark:prose-invert max-w-none w-full min-h-[240px] max-h-[44vh] overflow-y-auto px-3 py-2 border border-t-0 border-outline-gray-2 rounded-b-lg bg-surface-white"
					@change="(html) => (content = html)"
				/>

				<!-- The footer is assembled by the system at send time (Email Account
				     footer, System Settings' address, the standard footer), so it
				     can't be edited here — but it does go out, so show it. -->
				<div v-if="footer" class="rounded border border-outline-gray-2 bg-surface-gray-1 px-2.5 py-1.5">
					<p class="text-xs text-ink-gray-5">Footer added when sent</p>
					<div
						class="mt-1.5 max-h-24 overflow-y-auto border-t border-outline-gray-2 pt-1.5 text-xs text-ink-gray-6 [&_a]:underline"
						v-html="footer"
					/>
				</div>

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

				<div class="min-h-[28rem] rounded-md border border-outline-gray-2 bg-surface-white">
					<AvailabilityWeek :users="calendarUsers" :picked="pickedSlots" @toggle="toggleSlot" />
				</div>
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
import AvailabilityWeek from "@/components/AvailabilityWeek.vue"
import { formatDate } from "@spa/utils/datetime.js"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	lead: { type: Object, required: true },
	/** "new" | "reply" | "forward" */
	mode: { type: String, default: "new" },
	/** The communication being replied to / forwarded */
	source: { type: Object, default: null },
	/** Address to start a new email to, when it isn't the lead's own. */
	recipient: { type: String, default: "" },
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

const FIELD_LABELS = { recipients: "To", cc: "Cc", bcc: "Bcc" }

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
const calendarUsers = ref([])
/** Times chosen in the calendar column, offered as chips to drop in the body. */
const pickedSlots = ref([])
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

const chipsVisible = computed(
	() => Boolean(focusedField.value) && availableSuggestions.value.length > 0
)

const focusedLabel = computed(() => FIELD_LABELS[focusedField.value] || "To")

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

async function loadCalendarUsers() {
	if (calendarUsers.value.length) return
	try {
		calendarUsers.value = await call("phamos.api.sales_leads.get_lead_owners")
	} catch (e) {
		calendarUsers.value = []
	}
}

/** Straight off the slot, so the message says the time that was picked —
 *  these are naive local stamps, not something to re-interpret in a tz. */
function slotLabel(slot) {
	return `${formatDate(slot.starts_on.slice(0, 10))}, ${slot.starts_on.slice(
		11,
		16
	)}–${slot.ends_on.slice(11, 16)}`
}

function toggleSlot(slot) {
	const exists = pickedSlots.value.some((s) => s.starts_on === slot.starts_on)
	pickedSlots.value = exists
		? pickedSlots.value.filter((s) => s.starts_on !== slot.starts_on)
		: [...pickedSlots.value, slot].sort((a, b) => a.starts_on.localeCompare(b.starts_on))
}

/** Inserted above the signature, so the message still reads correctly. */
function insertLines(lines) {
	const sig = signature.value
	const body = content.value || ""
	const html = lines.join("")
	const at = sig ? body.lastIndexOf(`<p><br></p>${sig}`) : -1
	content.value = at === -1 ? body + html : body.slice(0, at) + html + body.slice(at)
}

/** The chips stay compact, but a time offered in a mail reads better with the
 *  day written out — "Thursday, 17.09.2026" is harder to misread than a date. */
function slotSentence(slot) {
	const date = new Date(`${slot.starts_on.slice(0, 10)}T00:00:00`)
	const weekday = date.toLocaleDateString(undefined, { weekday: "long" })
	return `${weekday}, ${slotLabel(slot)}`
}

function insertSlot(slot) {
	insertLines([`<p>${slotSentence(slot)}</p>`])
}

function insertAllSlots() {
	insertLines(pickedSlots.value.map((slot) => `<p>${slotSentence(slot)}</p>`))
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
	return { recipients: props.recipient || props.lead.email_id || "", subject: "", content: "" }
}

/** One draft per lead + what's being written, so a half-typed reply doesn't
 *  reappear inside a new email. Held in memory for the session, matching how
 *  Desk's own composer keeps its last edited communication. */
function draftKey() {
	return [props.lead.name, props.mode, props.source?.name || props.recipient || ""].join("|")
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
		pickedSlots.value = []
		loadCalendarUsers()

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
