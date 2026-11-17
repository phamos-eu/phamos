<template>
	<!-- New / edit a company appointment (#1949): a row of the General Management Department's Event Schedule. -->
	<Dialog :options="dialogOptions" :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
		<template #body-content>
			<form ref="formEl" class="space-y-4" @submit.prevent="save">
				<FormControl v-model="form.subject" :label="__('Subject')" type="text" size="sm" required />
				<div class="grid grid-cols-2 gap-3">
					<FormControl v-model="form.start" :label="__('Start')" type="datetime-local" size="sm" required />
					<FormControl v-model="form.end" :label="__('End')" type="datetime-local" size="sm" required />
				</div>
				<div class="grid grid-cols-2 gap-3">
					<FormControl v-model="form.location" :label="__('Location')" type="text" size="sm" />
					<FormControl
						v-model="form.email_account"
						:label="__('Sent from')"
						type="select"
						size="sm"
						:options="mailboxOptions"
						required
					/>
				</div>

				<div class="space-y-2 rounded border border-outline-gray-2 p-2.5">
					<FormControl v-model="form.repeat_this_event" :label="__('Repeat')" type="checkbox" size="sm" />
					<div v-if="form.repeat_this_event" class="space-y-2">
						<div class="grid grid-cols-2 gap-3">
							<FormControl v-model="form.repeat_on" type="select" size="sm" :options="repeatOptions" />
							<FormControl v-model="form.repeat_till" :label="__('Until')" type="date" size="sm" />
						</div>
						<div v-if="form.repeat_on === 'Weekly'" class="flex flex-wrap gap-1">
							<button
								v-for="(day, i) in WEEKDAYS"
								:key="day"
								type="button"
								class="rounded px-2 py-0.5 text-xs"
								:class="form[day] ? 'bg-surface-gray-7 text-ink-white' : 'bg-surface-gray-2 text-ink-gray-7'"
								:aria-pressed="Boolean(form[day])"
								@click="form[day] = form[day] ? 0 : 1"
							>
								{{ __(DAY_LABELS[i]) }}
							</button>
						</div>
					</div>
				</div>

				<div>
					<div class="mb-1.5 text-xs text-ink-gray-5">{{ __("Attendees") }}</div>
					<AttendeePicker v-model="attendees" :departments="options.departments || []" />
				</div>

				<FormControl v-model="form.description" :label="__('Description')" type="textarea" size="sm" :rows="3" />

				<div
					v-if="appointment?.sync_error"
					class="rounded border border-outline-red-1 bg-surface-red-1 px-2.5 py-2 text-xs text-ink-red-4"
				>
					{{ __("The invite was not sent: {0}", [appointment.sync_error]) }}
				</div>
				<ErrorMessage v-if="error" :message="error" />

				<div v-if="appointment?.name" class="border-t border-outline-gray-2 pt-3">
					<Button v-if="!confirmingCancel" theme="red" variant="subtle" @click="confirmingCancel = true">
						{{ __("Cancel appointment") }}
					</Button>
					<div v-else class="flex flex-wrap items-center gap-2 text-sm text-ink-red-4">
						<span>{{ __("This cancels the invite for all attendees") }}</span>
						<Button theme="red" variant="solid" :loading="deleting" @click="cancelAppointment">
							{{ __("Cancel appointment") }}
						</Button>
						<Button variant="subtle" @click="confirmingCancel = false">{{ __("Keep it") }}</Button>
					</div>
				</div>
			</form>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { Button, call, Dialog, ErrorMessage, FormControl } from "frappe-ui"
import AttendeePicker from "@spa/components/AttendeePicker.vue"
import { normalizeAttendees } from "@spa/utils/attendeePicker.js"
import { WEEKDAYS } from "@spa/utils/appointments.js"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "@/config"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	// An appointment from get_company_appointments to edit, or null for a new one.
	appointment: { type: Object, default: null },
	// New appointment: start and end to suggest ("YYYY-MM-DD HH:MM:SS"), e.g. from a calendar slot.
	suggested: { type: Object, default: () => ({}) },
	// get_appointment_options(): mailboxes and departments
	options: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:modelValue", "saved", "deleted"])

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
const REPEATS = ["Daily", "Weekly", "Monthly", "Yearly"]

const formEl = ref(null)
const form = ref({})
const attendees = ref({ required: [], optional: [] })
const saving = ref(false)
const deleting = ref(false)
const confirmingCancel = ref(false)
const error = ref("")

const mailboxOptions = computed(() => [
	{ label: __("Pick a mailbox…"), value: "" },
	...(props.options.mailboxes || []).map((m) => ({ label: m.email_id, value: m.name })),
])
const repeatOptions = computed(() => REPEATS.map((value) => ({ label: __(value), value })))

const dialogOptions = computed(() => ({
	title: props.appointment?.name ? __("Edit appointment") : __("New appointment"),
	size: "2xl",
	actions: [
		{ label: __("Close"), variant: "subtle", onClick: () => emit("update:modelValue", false) },
		{ label: saving.value ? __("Saving…") : __("Save and send"), variant: "solid", loading: saving.value, onClick: save },
	],
}))

/** "2026-12-01 10:00:00" <-> "2026-12-01T10:00" for datetime-local inputs. */
const toInput = (value) => (value ? String(value).replace(" ", "T").slice(0, 16) : "")
const fromInput = (value) => (value ? `${value.replace("T", " ")}:00`.slice(0, 19) : "")

function reset() {
	const a = props.appointment || {}
	form.value = {
		name: a.name || null,
		subject: a.subject || "",
		location: a.location || "",
		description: a.description || "",
		start: toInput(a.start || props.suggested.start),
		end: toInput(a.end || props.suggested.end),
		email_account: a.email_account || "",
		repeat_this_event: Boolean(a.repeat_this_event),
		repeat_on: a.repeat_on || "Weekly",
		repeat_till: a.repeat_till || "",
		...Object.fromEntries(WEEKDAYS.map((day) => [day, a[day] ? 1 : 0])),
	}
	attendees.value = normalizeAttendees({ required: a.required_attendees || [], optional: a.optional_attendees || [] })
	error.value = ""
	confirmingCancel.value = false
}

watch(
	() => props.modelValue,
	(open) => open && reset(),
	{ immediate: true }
)

async function save() {
	error.value = ""
	if (formEl.value && !formEl.value.reportValidity()) return
	saving.value = true
	try {
		const saved = await call(`${spaConfig.api}.save_appointment`, {
			appointment: {
				...form.value,
				start: fromInput(form.value.start),
				end: fromInput(form.value.end),
				repeat_this_event: form.value.repeat_this_event ? 1 : 0,
				repeat_on: form.value.repeat_this_event ? form.value.repeat_on : "",
				required_attendees: attendees.value.required,
				optional_attendees: attendees.value.optional,
			},
		})
		emit("saved", saved)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not save the appointment")
	} finally {
		saving.value = false
	}
}

async function cancelAppointment() {
	deleting.value = true
	try {
		await call(`${spaConfig.api}.delete_appointment`, { name: props.appointment.name })
		emit("deleted", props.appointment.name)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not cancel the appointment")
	} finally {
		deleting.value = false
	}
}
</script>
