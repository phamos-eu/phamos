<template>
	<!-- Company appointments (#1949): the Events table of the General Management Department's
	     Company, as a list or a calendar. Saving sends the Mailcow invites. -->
	<div class="flex h-full min-h-0 flex-col bg-surface-white dark:bg-surface-gray-1">
		<div class="flex flex-shrink-0 flex-wrap items-center gap-2 border-b border-outline-gray-2 bg-surface-gray-1 px-3 py-2 dark:bg-surface-gray-2">
			<div class="flex items-center rounded border border-outline-gray-2 bg-surface-gray-2 p-0.5" role="group">
				<button
					v-for="option in VIEWS"
					:key="option"
					type="button"
					class="whitespace-nowrap rounded px-2 py-0.5 text-xs"
					:class="
						view === option
							? 'bg-surface-white font-medium text-ink-gray-9 shadow-sm dark:bg-surface-gray-4'
							: 'text-ink-gray-5 hover:text-ink-gray-8'
					"
					:aria-pressed="view === option"
					@click="view = option"
				>
					{{ __(option) }}
				</button>
			</div>
			<FormControl v-if="view === 'List'" v-model="showPast" :label="__('Show past')" type="checkbox" size="sm" />
			<span v-if="company" class="text-xs text-ink-gray-5">{{ company }}</span>
			<Button class="ml-auto" variant="solid" size="sm" :disabled="Boolean(error)" @click="openNew()">
				<template #prefix><FeatherIcon name="plus" class="h-3.5 w-3.5" /></template>
				{{ __("New appointment") }}
			</Button>
		</div>

		<div v-if="error" class="flex flex-1 items-center justify-center px-6 text-center text-sm text-ink-red-4">
			{{ error }}
		</div>
		<div v-else-if="loading && !loaded" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">
			Loading…
		</div>

		<div v-else-if="view === 'List'" class="min-h-0 flex-1 overflow-y-auto">
			<div v-if="!listItems.length" class="px-6 py-10 text-center text-sm text-ink-gray-5">
				{{ __("No upcoming appointments") }}
			</div>
			<button
				v-for="item in listItems"
				:key="item.appointment.name"
				type="button"
				class="flex w-full items-start gap-4 border-b border-outline-gray-1 px-4 py-3 text-left hover:bg-surface-gray-2"
				:class="{ 'opacity-60': item.past }"
				@click="openEdit(item.appointment)"
			>
				<div class="w-28 flex-shrink-0">
					<div class="text-sm font-semibold text-ink-gray-9">{{ formatDay(item.start) }}</div>
					<div class="text-xs text-ink-gray-5">{{ formatTime(item.start) }} – {{ formatTime(item.end) }}</div>
				</div>
				<div class="min-w-0 flex-1">
					<div class="truncate text-sm font-medium text-ink-gray-9">{{ item.appointment.subject }}</div>
					<div class="mt-0.5 flex flex-wrap gap-x-3 text-xs text-ink-gray-5">
						<span v-if="item.appointment.location">{{ item.appointment.location }}</span>
						<span>{{ __("{0} attendees", [attendeeCount(item.appointment)]) }}</span>
						<span v-if="repeatText(item.appointment)">{{ repeatText(item.appointment) }}</span>
					</div>
				</div>
				<div class="flex-shrink-0 text-xs">
					<span v-if="item.appointment.sync_error" class="text-ink-red-4" :title="item.appointment.sync_error">
						{{ __("Not sent") }}
					</span>
					<span v-else-if="item.appointment.synced" class="text-ink-green-4">{{ __("Sent") }}</span>
					<span v-else class="text-ink-gray-5">{{ __("Pending") }}</span>
				</div>
			</button>
		</div>

		<div v-else class="gm-calendar min-h-0 flex-1 overflow-hidden p-3">
			<!-- frappe-ui's Calendar reads its events once, at mount: the key re-mounts it on changes. -->
			<Calendar
				:key="calendarKey"
				:events="calendarEvents"
				:config="CALENDAR_CONFIG"
				:on-click="onCalendarClick"
				:on-cell-dbl-click="onCellDblClick"
			/>
		</div>

		<AppointmentDialog
			v-model="dialogOpen"
			:appointment="editing"
			:suggested="suggested"
			:options="options"
			@saved="load"
			@deleted="load"
		/>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { Button, Calendar, call, FeatherIcon, FormControl } from "frappe-ui"
import AppointmentDialog from "../components/AppointmentDialog.vue"
import { listAppointments, occurrencesBetween, repeatFrequency, weeklyDays } from "@spa/utils/appointments.js"
import { formatDate } from "@spa/utils/datetime"
import { __ } from "@spa/utils/i18n.js"
import spaConfig from "@/config"

const VIEWS = ["List", "Calendar"]
const VIEW_KEY = "general-management-appointments-view"
const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
// No drag or resize in the calendar (out of scope, #1949); a click opens the dialog instead.
const CALENDAR_CONFIG = { defaultMode: "Month", isEditMode: false, enableShortcuts: false, showIcon: false }
// The calendar shows occurrences from a year back to two years ahead.
const CALENDAR_DAYS_BACK = 365
const CALENDAR_DAYS_AHEAD = 730

const view = ref(readView())
const showPast = ref(false)
const loading = ref(false)
const loaded = ref(false)
const error = ref("")
const company = ref("")
const appointments = ref([])
const options = ref({ mailboxes: [], departments: [] })
const dialogOpen = ref(false)
const editing = ref(null)
const suggested = ref({})
const calendarKey = ref(0)

function readView() {
	try {
		return window.localStorage.getItem(VIEW_KEY) === "Calendar" ? "Calendar" : "List"
	} catch {
		return "List"
	}
}

watch(view, (value) => {
	try {
		window.localStorage.setItem(VIEW_KEY, value)
	} catch {
		// Blocked storage: the view just isn't remembered.
	}
})

const listItems = computed(() => listAppointments(appointments.value, new Date(), showPast.value))

const calendarEvents = computed(() => {
	const now = new Date()
	const from = new Date(now.getTime() - CALENDAR_DAYS_BACK * 86400000)
	const to = new Date(now.getTime() + CALENDAR_DAYS_AHEAD * 86400000)
	return appointments.value.flatMap((a) =>
		occurrencesBetween(a, from, to).map(({ start, end }, i) => ({
			id: `${a.name}#${i}`,
			appointment: a.name,
			title: a.subject,
			participant: a.location || "",
			fromDate: start.toISOString(),
			toDate: end.toISOString(),
			color: "amber",
		}))
	)
})

function attendeeCount(a) {
	return (a.required_attendees?.length || 0) + (a.optional_attendees?.length || 0)
}

function repeatText(a) {
	const freq = repeatFrequency(a)
	if (!freq) return ""
	let text = __(freq)
	if (freq === "Weekly") text += ` (${weeklyDays(a).map((d) => __(DAY_LABELS[d])).join(", ")})`
	if (a.repeat_till) text += ` ${__("until {0}", [formatDate(a.repeat_till)])}`
	return text
}

function formatDay(date) {
	return date.toLocaleDateString(undefined, { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" })
}

function formatTime(date) {
	return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
}

const pad = (n) => String(n).padStart(2, "0")
const toFrappe = (d) =>
	`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:00`

/** New appointment, by default at the next full hour, one hour long. */
function openNew(start = null) {
	const from = start || new Date(Math.ceil(Date.now() / 3600000) * 3600000)
	editing.value = null
	suggested.value = { start: toFrappe(from), end: toFrappe(new Date(from.getTime() + 3600000)) }
	dialogOpen.value = true
}

function openEdit(appointment) {
	editing.value = appointment
	suggested.value = {}
	dialogOpen.value = true
}

function onCalendarClick({ calendarEvent }) {
	const appointment = appointments.value.find((a) => a.name === calendarEvent.appointment)
	if (appointment) openEdit(appointment)
}

/** Double-click on a free slot: a new appointment there (month view: 09:00 that day). */
function onCellDblClick({ date, time }) {
	const start = new Date(date)
	if (time) {
		const [hh, mm] = String(time).split(":").map(Number)
		start.setHours(hh || 0, mm || 0, 0, 0)
	} else {
		start.setHours(9, 0, 0, 0)
	}
	openNew(start)
}

async function load() {
	loading.value = true
	try {
		const [data, opts] = await Promise.all([
			call(`${spaConfig.api}.get_company_appointments`),
			call(`${spaConfig.api}.get_appointment_options`),
		])
		company.value = data.company
		appointments.value = data.appointments
		options.value = opts
		error.value = ""
		calendarKey.value++
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not load the appointments")
	} finally {
		loading.value = false
		loaded.value = true
	}
}

onMounted(load)
</script>

<style>
/* frappe-ui 0.1.105's Calendar hard-codes light Tailwind colours (bg-white day numbers, gray
   text and borders); follow the cockpit theme in dark mode instead. Unscoped on purpose: Vue's
   scoped :global() drops the rest of the selector, which would recolour the whole page. */
[data-theme="dark"] .gm-calendar .bg-white {
	background-color: var(--surface-gray-1);
}

[data-theme="dark"] .gm-calendar .text-gray-700,
[data-theme="dark"] .gm-calendar .text-gray-600 {
	color: var(--ink-gray-7);
}

[data-theme="dark"] .gm-calendar .border-gray-200 {
	border-color: var(--outline-gray-2);
}
</style>
