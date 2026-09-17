<template>
	<Dialog
		:options="{
			title: `Create Demo — ${lead.lead_name || lead.name}`,
			size: '6xl',
			actions: [
				{ label: 'Cancel', variant: 'subtle', onClick: () => emit('update:modelValue', false) },
				{
					label: saving ? 'Creating…' : 'Create Demo',
					variant: 'solid',
					loading: saving,
					onClick: submit,
				},
			],
		}"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-4">
				<FormControl v-model="subject" label="Subject" type="text" size="sm" required />

				<!-- Two columns at width so the dialog grows sideways rather than
				     into a long scroll; stacks again on narrow viewports. -->
				<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
				<section class="rounded-md border border-outline-gray-2 p-3">
					<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
						Appointment
					</div>
					<div class="grid grid-cols-2 gap-3">
						<FormControl v-model="day" label="Day" type="date" size="sm" />
						<FormControl
							v-model="durationMinutes"
							label="Duration"
							type="select"
							size="sm"
							:options="durationOptions"
						/>
					</div>

					<div class="mt-3">
						<DemoCalendarPreview
							:day="day"
							:duration-minutes="durationMinutes"
							:users="owners"
							:proposals="proposals"
							@propose="toggleProposal"
						/>
					</div>

					<div class="mt-3 grid grid-cols-[1fr_1fr_auto] items-end gap-3">
						<div>
							<label class="mb-1.5 block text-xs text-ink-gray-5">Starts On</label>
							<input
								v-model="startsOn"
								type="datetime-local"
								class="form-input block h-8 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8"
							/>
						</div>
						<div>
							<label class="mb-1.5 block text-xs text-ink-gray-5">Ends On</label>
							<input
								v-model="endsOn"
								type="datetime-local"
								class="form-input block h-8 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8"
							/>
						</div>
						<Button :disabled="!startsOn" @click="addManualProposal">Propose</Button>
					</div>

					<div class="mt-3">
						<div class="mb-1.5 text-xs text-ink-gray-5">
							Proposed dates
							<span v-if="proposals.length > 1" class="text-ink-gray-6">
								— the customer picks one
							</span>
						</div>
						<div v-if="!proposals.length" class="text-xs text-ink-gray-5">
							None yet. Pick a slot above, or add one manually.
						</div>
						<div v-else class="space-y-1.5">
							<div
								v-for="(proposal, index) in proposals"
								:key="proposal.starts_on"
								class="flex items-center gap-2 rounded-md border border-outline-gray-2 px-2.5 py-1.5 text-sm text-ink-gray-8"
							>
								<FeatherIcon name="calendar" class="h-3.5 w-3.5 flex-shrink-0 text-ink-gray-5" />
								<span class="min-w-0 flex-1 truncate">{{ proposalLabel(proposal) }}</span>
								<button
									type="button"
									class="flex-none rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-9"
									title="Remove"
									@click="proposals.splice(index, 1)"
								>
									<FeatherIcon name="x" class="h-3.5 w-3.5" />
								</button>
							</div>
						</div>
					</div>
				</section>

				<div class="space-y-4">
				<section class="rounded-md border border-outline-gray-2 p-3">
					<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
						Invitees
					</div>

					<div v-if="participants.length" class="mb-2 space-y-1.5">
						<div
							v-for="(participant, index) in participants"
							:key="index"
							class="flex items-center gap-1.5"
						>
							<input
								v-model="participant.email"
								type="email"
								placeholder="name@example.com"
								class="form-input h-7 min-w-0 flex-1 rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8"
							/>
							<select
								v-model="participant.participation"
								class="form-select h-7 w-28 flex-none rounded border border-outline-gray-2 bg-surface-white px-1.5 text-xs text-ink-gray-8"
							>
								<option value="Required">Required</option>
								<option value="Optional">Optional</option>
							</select>
							<button
								type="button"
								class="flex-none rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-9"
								title="Remove"
								@click="participants.splice(index, 1)"
							>
								<FeatherIcon name="x" class="h-3.5 w-3.5" />
							</button>
						</div>
					</div>

					<div class="flex flex-wrap items-center gap-1.5">
						<button
							type="button"
							class="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
							@click="addParticipant()"
						>
							<FeatherIcon name="plus" class="h-3.5 w-3.5" />
							<span>Add invitee</span>
						</button>
						<span v-if="colleagueOptions.length" class="text-xs text-ink-gray-5">or</span>
						<button
							v-for="user in colleagueOptions"
							:key="user.name"
							type="button"
							class="rounded-full border border-outline-gray-2 px-2 py-0.5 text-xs text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
							@click="addParticipant(user.name, 'Required', user.name)"
						>
							+ {{ user.full_name || user.name }}
						</button>
					</div>
				</section>

				<div>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Location</label>
					<div class="flex items-start gap-1.5">
						<FormControl
							v-model="location"
							type="textarea"
							size="sm"
							rows="2"
							placeholder="Street address, or a video link for an online meeting"
							class="min-w-0 flex-1"
						/>
						<Button title="Generate a video meeting link" @click="generateVideoLink">
							Video link
						</Button>
					</div>
				</div>

				<!-- Draft-only: the selection isn't persisted (see demoModules.js). -->
				<section class="rounded-md border border-outline-gray-2 p-3">
					<div class="mb-2 flex items-center justify-between">
						<span class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
							Modules to demo
						</span>
						<span class="text-xs text-ink-gray-5">{{ selectedModules.length }} selected</span>
					</div>
					<div class="max-h-64 overflow-y-auto">
						<table class="w-full text-sm">
							<tbody>
								<tr
									v-for="module in DEMO_MODULES"
									:key="module.key"
									class="cursor-pointer border-b border-outline-gray-1 last:border-0 hover:bg-surface-gray-2"
									@click="toggleModule(module.key)"
								>
									<td class="w-8 py-1.5 pl-1">
										<input
											type="checkbox"
											class="h-4 w-4 rounded border-outline-gray-3"
											:checked="selectedModules.includes(module.key)"
											@click.stop
											@change="toggleModule(module.key)"
										/>
									</td>
									<td class="py-1.5 font-medium text-ink-gray-8">{{ module.label }}</td>
									<td class="py-1.5 text-xs text-ink-gray-6">{{ module.description }}</td>
								</tr>
							</tbody>
						</table>
					</div>
				</section>

				<FormControl
					v-model="agenda"
					label="Agenda"
					type="textarea"
					size="sm"
					rows="3"
					placeholder="What will be shown, who is attending…"
				/>
				</div>
				</div>

				<ErrorMessage :message="error" />
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call } from "frappe-ui"
import { DEMO_MODULES } from "@/demoModules.js"
import DemoCalendarPreview from "./DemoCalendarPreview.vue"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	lead: { type: Object, required: true },
})

const emit = defineEmits(["update:modelValue", "created"])

const subject = ref("")
const day = ref("")
const durationMinutes = ref("60")
const startsOn = ref("")
const endsOn = ref("")
const agenda = ref("")
const location = ref("")
const selectedModules = ref([])
// Several dates can be offered while the demo isn't pinned down yet.
const proposals = ref([])

const owners = ref([])
// Invitees: a `user` makes it an Event participant row; email-only invitees
// can't be (Event Participants requires a linked record) so they ride along
// in the attendee fields instead.
const participants = ref([])
const saving = ref(false)
const error = ref("")

const durationOptions = [15, 30, 45, 60, 90, 120].map((m) => ({ label: `${m} minutes`, value: String(m) }))

const defaultSubject = computed(
	() => `Demo — ${props.lead?.company_name || props.lead?.lead_name || props.lead?.name || ""}`.trim()
)

watch(
	() => props.modelValue,
	(open) => {
		if (!open) return
		subject.value = defaultSubject.value
		// Local date, not toISOString(): that is UTC, so before 02:00 in Berlin
		// the calendar would open on yesterday.
		const now = new Date()
		day.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(
			now.getDate()
		).padStart(2, "0")}`
		durationMinutes.value = "60"
		startsOn.value = ""
		endsOn.value = ""
		agenda.value = ""
		location.value = ""
		selectedModules.value = []
		proposals.value = []
		error.value = ""
		participants.value = props.lead?.email_id
			? [{ email: props.lead.email_id, participation: "Required", user: null }]
			: []
		loadOwners()
	}
)

/** Colleagues not already invited, offered as one-click adds. */
const colleagueOptions = computed(() =>
	owners.value.filter((u) => !participants.value.some((p) => p.email === u.name))
)

async function loadOwners() {
	if (owners.value.length) return
	try {
		owners.value = await call("phamos.api.sales_leads.get_lead_owners")
	} catch (e) {
		owners.value = []
	}
}

function toggleModule(key) {
	const index = selectedModules.value.indexOf(key)
	if (index === -1) selectedModules.value.push(key)
	else selectedModules.value.splice(index, 1)
}

/** Slots come back as naive local 'YYYY-MM-DD HH:mm:ss'; the inputs want a T. */
function toInputValue(value) {
	return (value || "").replace(" ", "T").slice(0, 16)
}

/** ...and the backend wants the space-separated form back. */
function toApiValue(value) {
	if (!value) return null
	return `${value.replace("T", " ")}:00`.slice(0, 19)
}

function sortProposals() {
	proposals.value.sort((a, b) => String(a.starts_on).localeCompare(String(b.starts_on)))
}

function isProposed(startLocal) {
	return proposals.value.some((p) => p.starts_on === startLocal)
}

function toggleProposal(slot) {
	const index = proposals.value.findIndex((p) => p.starts_on === slot.starts_on)
	if (index !== -1) {
		proposals.value.splice(index, 1)
		return
	}
	proposals.value.push({ starts_on: slot.starts_on, ends_on: slot.ends_on })
	sortProposals()
}

function addParticipant(email = "", participation = "Required", user = null) {
	participants.value.push({ email, participation, user })
}

function addManualProposal() {
	const starts = toApiValue(startsOn.value)
	if (!starts || isProposed(starts)) return
	proposals.value.push({ starts_on: starts, ends_on: toApiValue(endsOn.value) })
	sortProposals()
	startsOn.value = ""
	endsOn.value = ""
}

function proposalLabel(proposal) {
	return proposal.ends_on ? `${proposal.starts_on} – ${proposal.ends_on.slice(11, 16)}` : proposal.starts_on
}

/** Same throwaway-room scheme the Desk hybrid meeting composer uses. */
function generateVideoLink() {
	const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
	// The room name is the only thing keeping strangers out of the meeting, so
	// it comes from the CSPRNG rather than Math.random(), whose state is
	// recoverable from a handful of observed outputs.
	const bytes = crypto.getRandomValues(new Uint8Array(15))
	let room = ""
	for (const byte of bytes) room += chars[byte % chars.length]
	location.value = `https://meet.jit.si/${room}`
}

async function submit() {
	error.value = ""
	if (!subject.value.trim()) {
		error.value = "Subject is required"
		return
	}

	const modules = DEMO_MODULES.filter((m) => selectedModules.value.includes(m.key)).map((m) => m.label)
	const agendaText = [agenda.value.trim(), modules.length ? `Modules: ${modules.join(", ")}` : ""]
		.filter(Boolean)
		.join("\n\n")

	saving.value = true
	try {
		const demo = await call("phamos.api.sales_demos.create_demo", {
			lead: props.lead.name,
			subject: subject.value.trim(),
			slots: proposals.value,
			participants: participants.value.filter((p) => (p.email || "").trim()),
			location: location.value.trim() || null,
			agenda: agendaText || null,
		})
		emit("created", demo)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not create demo"
	} finally {
		saving.value = false
	}
}
</script>
