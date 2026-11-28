<template>
	<!-- The Team Cockpit's start page (#2236): one short tile per page, each linking to it. One
	     screen, no page scroll: the tiles share the height, and a long list is cut, not scrolled. -->
	<div class="grid h-full min-h-0 auto-rows-fr grid-cols-1 gap-3 overflow-hidden bg-surface-gray-1 p-4 sm:grid-cols-2 xl:grid-cols-3">
		<div v-if="error" class="col-span-full rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
			{{ error }}
		</div>

		<template v-else>
			<!-- Who is here today -->
			<OverviewTile :title="__('Who is here today')" :to="{ name: 'TeamMates' }" :loading="loading" :missing="data.mates === null">
				<template #actions>
					<IssueChatButton v-if="data.team" doctype="Team" :record-name="data.team" :subject="data.team" :api="spaConfig.api" />
				</template>
				<p class="text-sm text-ink-gray-7">
					{{ __("{0} of {1} checked in", [checkedIn.length, (data.mates || []).length]) }}
				</p>
				<ul class="mt-2 min-h-0 space-y-1 overflow-hidden">
					<li v-for="row in data.mates" :key="row.employee" class="flex items-center gap-2 text-sm">
						<Avatar :label="row.employee_name" :image="row.image" size="sm" />
						<span class="min-w-0 flex-1 truncate text-ink-gray-8">{{ row.employee_name }}</span>
						<span v-if="row.focus" class="text-xs text-ink-blue-3">{{ __("In focus") }}</span>
						<span class="text-xs" :class="presenceClass(row)">{{ presenceLabel(row) }}</span>
					</li>
				</ul>
			</OverviewTile>

			<!-- Next appointment and today's absences -->
			<OverviewTile :title="__('Next appointment')" :to="{ name: 'TeamAppointments' }" :loading="loading" :missing="data.appointments === null">
				<template v-if="nextAppointment">
					<p class="truncate text-sm font-medium text-ink-gray-9">{{ nextAppointment.appointment.subject }}</p>
					<p class="text-xs text-ink-gray-6">
						{{ formatWhen(nextAppointment.start) }}<span v-if="nextAppointment.appointment.location"> · {{ nextAppointment.appointment.location }}</span>
					</p>
				</template>
				<p v-else class="text-sm text-ink-gray-5">{{ __("No upcoming appointments") }}</p>
				<p class="mt-3 text-xs font-medium uppercase tracking-wide text-ink-gray-5">{{ __("Today") }}</p>
				<ul class="mt-1 min-h-0 space-y-0.5 overflow-hidden text-sm">
					<li v-for="h in absences.holidays" :key="h.description" class="truncate text-ink-gray-7">🎉 {{ h.description }}</li>
					<li v-for="a in absences.absences" :key="a.employee" class="truncate text-ink-gray-7">
						{{ a.half_day_date ? __("{0} is absent (half day)", [a.employee_name]) : __("{0} is absent", [a.employee_name]) }}
					</li>
					<li v-if="!absences.holidays.length && !absences.absences.length" class="text-ink-gray-5">{{ __("Nobody is absent") }}</li>
				</ul>
			</OverviewTile>

			<!-- Hours this month -->
			<OverviewTile :title="__('Hours this month')" :to="{ name: 'TeamStatistics' }" :loading="loading" :missing="data.hours === null">
				<template v-if="data.hours">
					<p class="text-2xl font-semibold text-ink-gray-9">
						{{ hoursLabel(data.hours.logged) }}
						<span class="text-sm font-normal text-ink-gray-6">{{ __("of {0} available", [hoursLabel(data.hours.available)]) }}</span>
					</p>
					<dl class="mt-3 grid grid-cols-2 gap-2 text-sm">
						<div>
							<dt class="text-xs text-ink-gray-5">{{ __("Booked") }}</dt>
							<dd class="font-medium text-ink-gray-8">{{ percentLabel(data.hours.booked_rate) }}</dd>
						</div>
						<div>
							<dt class="text-xs text-ink-gray-5">{{ __("Billable") }}</dt>
							<dd class="font-medium text-ink-gray-8">{{ percentLabel(data.hours.billable_rate) }}</dd>
						</div>
					</dl>
				</template>
			</OverviewTile>

			<!-- GitLab this month -->
			<OverviewTile :title="__('GitLab this month')" :to="{ name: 'TeamGitlab' }" :loading="loading" :missing="data.gitlab === null">
				<dl v-if="data.gitlab" class="grid grid-cols-3 gap-2">
					<div v-for="figure in gitlabFigures" :key="figure.label">
						<dd class="text-2xl font-semibold text-ink-gray-9">{{ figure.value }}</dd>
						<dt class="text-xs text-ink-gray-5">{{ figure.label }}</dt>
					</div>
				</dl>
			</OverviewTile>

			<!-- Latest successes -->
			<OverviewTile :title="__('Latest successes')" :to="{ name: 'TeamSuccesses' }" :loading="loading" :missing="data.successes === null">
				<ul class="min-h-0 space-y-1.5 overflow-hidden">
					<li v-for="row in data.successes" :key="row.name" class="text-sm">
						<div class="truncate text-ink-gray-9">🎉 {{ row.title }}</div>
						<div class="text-xs text-ink-gray-5">{{ __(row.success_type) }} · {{ formatDate(row.date) }}</div>
					</li>
					<li v-if="!(data.successes || []).length" class="text-sm text-ink-gray-5">{{ __("No successes yet") }}</li>
				</ul>
			</OverviewTile>

			<!-- Needs attention -->
			<OverviewTile :title="__('Needs attention')" :to="{ name: 'TeamAttention' }" :loading="loading" :missing="data.attention === null">
				<template v-if="data.attention">
					<p class="text-sm text-ink-gray-7">
						{{ attentionCount ? __("{0} records", [attentionCount]) : __("Nothing needs attention.") }}
					</p>
					<ul class="mt-2 min-h-0 space-y-1.5 overflow-hidden">
						<li v-for="item in data.attention.items" :key="`${item.doctype}:${item.name}`" class="text-sm">
							<router-link :to="recordRoute(item)" class="block truncate text-ink-gray-9 hover:underline">
								{{ ICONS[item.kind] || "💤" }} {{ item.title || item.name }}
							</router-link>
							<div class="text-xs" :class="item.kind.endsWith('_missed') ? 'text-ink-red-4' : 'text-ink-gray-5'">{{ item.detail }}</div>
						</li>
					</ul>
				</template>
			</OverviewTile>
		</template>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue"
import { Avatar, call } from "frappe-ui"
import IssueChatButton from "@spa/components/IssueChatButton.vue"
import { listAppointments } from "@spa/utils/appointments.js"
import { formatDate } from "@spa/utils/datetime"
import { __ } from "@spa/utils/i18n.js"
import OverviewTile from "../components/OverviewTile.vue"
import spaConfig from "../config"

// the same emoji as the Needs attention page
const ICONS = { response_missed: "⏰", resolution_missed: "⏰", response_due: "⏳", resolution_due: "⏳", idle: "💤" }

const loading = ref(true)
const error = ref("")
const data = ref({})

const checkedIn = computed(() => (data.value.mates || []).filter((r) => r.presence === "checked_in"))
const nextAppointment = computed(() => listAppointments(data.value.appointments || [], new Date())[0] || null)
const absences = computed(() => ({
	holidays: data.value.absences?.holidays || [],
	absences: data.value.absences?.absences || [],
}))
const attentionCount = computed(() =>
	data.value.attention ? `${data.value.attention.count}${data.value.attention.truncated ? "+" : ""}` : 0
)
const gitlabFigures = computed(() => [
	{ label: __("Items closed"), value: data.value.gitlab?.closed ?? "—" },
	{ label: __("Items opened"), value: data.value.gitlab?.opened ?? "—" },
	{ label: __("Merge requests merged"), value: data.value.gitlab?.merged ?? "—" },
])

function presenceLabel(row) {
	switch (row.presence) {
		case "absent":
			return __("Absent")
		case "holiday":
			return __("Public holiday")
		case "day_off":
			return __("Day off")
		case "checked_in":
			return __("Checked in since {0}", [row.since])
		default:
			return __("Not checked in")
	}
}

function presenceClass(row) {
	if (row.presence === "checked_in") return "text-ink-green-3"
	if (["absent", "holiday", "day_off"].includes(row.presence)) return "text-ink-amber-3"
	return "text-ink-gray-5"
}

const numberFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 })

function hoursLabel(value) {
	return value == null ? "—" : `${numberFormat.format(value)} h`
}

function percentLabel(value) {
	return value == null ? "—" : `${numberFormat.format(value)} %`
}

function formatWhen(date) {
	return date.toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
}

function recordRoute(item) {
	return item.doctype === "Task"
		? { name: "TaskDetail", params: { name: item.name } }
		: { name: "IssueDetail", params: { name: item.name } }
}

async function load() {
	try {
		data.value = await call(`${spaConfig.api}.get_team_overview`)
		error.value = ""
	} catch (e) {
		error.value = e.messages?.[0] || e.message || __("Could not load the overview.")
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>
