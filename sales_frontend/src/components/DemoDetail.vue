<template>
	<div class="flex h-full min-h-0 w-full">
		<div v-if="loading" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">Loading…</div>
		<template v-else-if="demo">
			<!-- The appointment itself: what it is, when, and where to join. -->
			<section class="w-72 flex-none space-y-4 overflow-y-auto border-r border-outline-gray-2 bg-surface-white p-4">
				<FormControl v-model="subject" label="Subject" type="text" size="sm" />

				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Lead</label>
					<RouterLink
						:to="{ name: 'LeadDetail', params: { name: demo.lead } }"
						class="text-sm text-ink-gray-8 underline-offset-2 hover:underline"
					>
						{{ demo.lead_name || demo.lead }}
					</RouterLink>
				</div>

				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Scheduled</label>
					<input
						v-model="scheduledOn"
						type="datetime-local"
						class="form-input block h-8 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8"
					/>
				</div>
				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Ends</label>
					<input
						v-model="endsOn"
						type="datetime-local"
						class="form-input block h-8 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8"
					/>
				</div>

				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Next Follow Up</label>
					<DatePicker
						:model-value="nextFollowup"
						placeholder="Date"
						@update:model-value="onFollowupChange"
					/>
					<p class="mt-1 text-xs text-ink-gray-5">Also sets the follow-up on the lead.</p>
				</div>

				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Location or meeting link</label>
					<FormControl v-model="location" type="textarea" rows="2" size="sm" />
					<!-- Only when the field really holds a URL — it doubles as a street address. -->
					<a
						v-if="demo.meeting_url"
						:href="demo.meeting_url"
						target="_blank"
						rel="noopener"
						class="mt-1.5 flex w-full items-center justify-center gap-1.5 rounded-md bg-surface-gray-7 px-2 py-1.5 text-sm font-medium text-ink-white hover:bg-surface-gray-6"
					>
						<FeatherIcon name="video" class="h-3.5 w-3.5" />
						<span>Join Meeting</span>
					</a>
				</div>

				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Nextcloud Link</label>
					<FormControl v-model="nextcloudLink" type="text" size="sm" placeholder="https://…" />
					<a
						v-if="demo.nextcloud_url"
						:href="demo.nextcloud_url"
						target="_blank"
						rel="noopener"
						class="mt-1 flex items-center gap-1.5 text-xs text-ink-gray-6 hover:text-ink-gray-9"
					>
						<FeatherIcon name="film" class="h-3.5 w-3.5" />
						<span>Open recording</span>
					</a>
				</div>

				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Agenda</label>
					<FormControl v-model="agenda" type="textarea" rows="4" size="sm" />
				</div>
			</section>

			<!-- People and what they made of it. -->
			<section class="flex min-w-0 flex-1 flex-col overflow-hidden bg-surface-gray-1">
				<div class="flex flex-shrink-0 flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-outline-gray-2 bg-surface-white px-4 py-3">
					<span class="text-base font-semibold text-ink-gray-9">{{ demo.subject }}</span>
					<span v-if="demo.scheduled_on" class="text-sm text-ink-gray-6">
						{{ formatDatetime(demo.scheduled_on) }}
					</span>
					<span v-else class="text-sm text-ink-amber-3">Not scheduled yet</span>
				</div>

				<div class="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
					<DemoAttendeeEditor
						:model-value="attendees"
						:lead="demo.lead"
						@update:model-value="saveAttendees"
					/>

					<div>
						<div class="mb-2 flex items-center justify-between gap-2">
							<span class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
								Feedback
							</span>
							<Button variant="subtle" size="sm" @click="openFeedback(null)">
								<template #prefix><FeatherIcon name="plus" class="h-3.5 w-3.5" /></template>
								Add feedback
							</Button>
						</div>

						<div v-if="!feedback.length" class="rounded-md border border-outline-gray-2 bg-surface-white p-4 text-center text-sm text-ink-gray-5">
							Nothing captured yet. Add what the attendees made of the demo.
						</div>

						<div v-else class="space-y-2">
							<div
								v-for="entry in feedback"
								:key="entry.name"
								class="rounded-md border border-l-2 border-outline-gray-2 bg-surface-white px-3 py-2.5"
								:class="entry.audience === 'External' ? 'border-l-teal-500' : 'border-l-blue-500'"
							>
								<div class="mb-1.5 flex items-center gap-2 text-xs text-ink-gray-5">
									<Badge
										:label="entry.audience"
										:theme="entry.audience === 'External' ? 'green' : 'blue'"
										size="sm"
										variant="subtle"
									/>
									<span class="min-w-0 truncate font-medium text-ink-gray-7">
										{{ entry.respondent_name }}
									</span>
									<span class="whitespace-nowrap">{{ formatDatetime(entry.modified) }}</span>
									<span class="ml-auto flex flex-none items-center gap-1">
										<button
											type="button"
											title="Edit"
											class="rounded p-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
											@click="openFeedback(entry)"
										>
											<FeatherIcon name="edit-2" class="h-3.5 w-3.5" />
										</button>
										<button
											type="button"
											title="Delete"
											class="rounded p-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-red-4"
											@click="removeFeedback(entry)"
										>
											<FeatherIcon name="trash-2" class="h-3.5 w-3.5" />
										</button>
									</span>
								</div>
								<div v-if="entry.modules.length" class="mb-1.5 flex flex-wrap gap-1.5">
									<span
										v-for="row in entry.modules"
										:key="row.module"
										class="rounded-full bg-surface-gray-3 px-2 py-0.5 text-xs text-ink-gray-9"
									>
										{{ row.module_name || row.module }}
									</span>
								</div>
								<div v-if="entry.notes" class="prose-sm max-w-none text-sm text-ink-gray-8" v-html="entry.notes" />
							</div>
						</div>
					</div>
				</div>
			</section>

			<!-- Status, the slots still on the table, and the prep checklist. -->
			<section class="flex w-72 flex-none flex-col gap-5 overflow-y-auto border-l border-outline-gray-2 bg-surface-white p-4">
				<section>
					<div class="mb-2 flex items-center justify-between gap-2">
						<span class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Status</span>
						<button
							type="button"
							class="rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-9"
							title="Back to list"
							@click="emit('close')"
						>
							<FeatherIcon name="x" class="h-4 w-4" />
						</button>
					</div>
					<div class="flex flex-wrap items-center gap-2">
						<button
							v-for="s in DEMO_STATUSES"
							:key="s"
							type="button"
							class="rounded-full disabled:opacity-50"
							:disabled="saving"
							@click="setStatus(s)"
						>
							<Badge
								:label="s"
								:theme="demoStatusTheme(s)"
								size="sm"
								:variant="status === s ? 'solid' : 'subtle'"
							/>
						</button>
					</div>
				</section>

				<section v-if="demo.proposed_slots.length">
					<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
						Proposed slots
					</div>
					<div class="space-y-1.5">
						<div
							v-for="slot in demo.proposed_slots"
							:key="slot.name"
							class="flex items-center gap-2 rounded border border-outline-gray-2 px-2 py-1.5"
						>
							<span class="min-w-0 flex-1 truncate text-xs text-ink-gray-8">
								{{ formatDatetime(slot.starts_on) }}
							</span>
							<!-- Confirming releases the other holds, so it only shows while
							     there is still a choice to make. -->
							<Button
								v-if="demo.proposed_slots.length > 1"
								size="sm"
								variant="subtle"
								:loading="confirming === slot.name"
								@click="confirmSlot(slot)"
							>
								Confirm
							</Button>
							<Badge v-else-if="demo.scheduled_on" label="Confirmed" theme="green" size="sm" variant="subtle" />
						</div>
					</div>
				</section>

				<LinkedChecklistsSection
					:key="demo.name"
					document="Demo"
					:reference-record="demo.name"
					:reference-title="demo.subject"
					:allow-create="demo.status !== 'Cancelled'"
				/>

				<ErrorMessage :message="error" />

				<a
					:href="demo.desk_url"
					target="_blank"
					rel="noopener"
					class="mt-auto text-xs text-ink-gray-6 hover:text-ink-gray-9"
				>
					Open in Desk
				</a>
			</section>
		</template>

		<DemoFeedbackDialog
			v-if="demo"
			v-model="showFeedbackDialog"
			:demo="demo"
			:entry="editingFeedback"
			@saved="loadFeedback"
		/>
	</div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue"
import { RouterLink } from "vue-router"
import { call, debounce, toast, Badge, DatePicker } from "frappe-ui"
import { formatDatetime } from "@spa/utils/datetime"
import LinkedChecklistsSection from "@spa/components/LinkedChecklistsSection.vue"
import DemoAttendeeEditor from "./DemoAttendeeEditor.vue"
import DemoFeedbackDialog from "./DemoFeedbackDialog.vue"
import { DEMO_STATUSES, demoStatusTheme } from "@/demoListColumns.js"

const API = "phamos.api.sales_demos"

const props = defineProps({
	name: { type: String, required: true },
})

const emit = defineEmits(["close", "updated"])

const loading = ref(false)
const saving = ref(false)
const error = ref("")
const demo = ref(null)
const feedback = ref([])
const attendees = ref([])
const confirming = ref("")
const showFeedbackDialog = ref(false)
const editingFeedback = ref(null)

const subject = ref("")
const scheduledOn = ref("")
const endsOn = ref("")
const location = ref("")
const agenda = ref("")
const status = ref("")
const nextFollowup = ref("")
const nextcloudLink = ref("")

/** Guards the watcher while fields are being filled from the server. */
const syncing = ref(false)

/** Datetime-local wants 'YYYY-MM-DDTHH:mm'; the API speaks the stored format. */
function toInputValue(value) {
	return value ? String(value).replace(" ", "T").slice(0, 16) : ""
}

function toApiValue(value) {
	return value ? `${String(value).replace("T", " ")}:00`.slice(0, 19) : null
}

function syncFields() {
	syncing.value = true
	subject.value = demo.value.subject || ""
	scheduledOn.value = toInputValue(demo.value.scheduled_on)
	endsOn.value = toInputValue(demo.value.ends_on)
	location.value = demo.value.location || ""
	agenda.value = demo.value.agenda || ""
	status.value = demo.value.status || ""
	nextFollowup.value = demo.value.next_followup || ""
	nextcloudLink.value = demo.value.nextcloud_link || ""
	attendees.value = demo.value.attendees || []
	setTimeout(() => (syncing.value = false), 0)
}

async function loadDemo() {
	loading.value = true
	try {
		demo.value = await call(`${API}.get_demo`, { name: props.name })
		syncFields()
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load the demo"
	} finally {
		loading.value = false
	}
}

async function loadFeedback() {
	try {
		feedback.value = await call(`${API}.get_demo_feedback`, { demo: props.name })
	} catch (e) {
		feedback.value = []
	}
}

async function saveFields(extra = {}) {
	if (!demo.value) return
	saving.value = true
	error.value = ""
	try {
		const result = await call(`${API}.update_demo`, {
			name: props.name,
			if_modified: demo.value.modified,
			subject: subject.value,
			scheduled_on: toApiValue(scheduledOn.value),
			ends_on: toApiValue(endsOn.value),
			location: location.value,
			agenda: agenda.value,
			status: status.value,
			next_followup: nextFollowup.value || null,
			nextcloud_link: nextcloudLink.value || null,
			...extra,
		})
		if (result.conflict) {
			toast({
				title: "This demo changed elsewhere — reloading",
				icon: "alert-triangle",
				iconClasses: "text-ink-amber-3",
			})
			demo.value = result.demo
			syncFields()
			return
		}
		demo.value = result.demo
		syncFields()
		emit("updated", demo.value)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not save"
	} finally {
		saving.value = false
	}
}

const scheduleSave = debounce(() => saveFields(), 500)

/** Saved immediately: it also moves the lead's follow-up, so it shouldn't
 *  sit in a debounce waiting for another keystroke. */
function onFollowupChange(value) {
	nextFollowup.value = value || ""
	saveFields({ next_followup: value || null })
}

function setStatus(value) {
	status.value = value
	saveFields({ status: value })
}

async function saveAttendees(rows) {
	attendees.value = rows
	try {
		demo.value = await call(`${API}.set_demo_attendees`, {
			name: props.name,
			rows: JSON.stringify(rows),
		})
		syncFields()
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not save the attendees"
	}
}

async function confirmSlot(slot) {
	confirming.value = slot.name
	error.value = ""
	try {
		demo.value = await call(`${API}.confirm_demo_slot`, { name: props.name, slot: slot.name })
		syncFields()
		emit("updated", demo.value)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not confirm the slot"
	} finally {
		confirming.value = ""
	}
}

function openFeedback(entry) {
	editingFeedback.value = entry
	showFeedbackDialog.value = true
}

async function removeFeedback(entry) {
	try {
		await call(`${API}.delete_demo_feedback`, { name: entry.name })
		loadFeedback()
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not delete the feedback"
	}
}

watch([subject, scheduledOn, endsOn, location, agenda, nextcloudLink], () => {
	if (syncing.value || !demo.value) return
	scheduleSave()
})

watch(
	() => props.name,
	() => {
		loadDemo()
		loadFeedback()
	}
)

onMounted(() => {
	loadDemo()
	loadFeedback()
})
</script>
