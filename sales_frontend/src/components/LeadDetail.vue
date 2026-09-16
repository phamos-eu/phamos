<template>
	<div class="flex h-full min-h-0 w-full">
		<div v-if="loading" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">Loading…</div>
		<template v-else-if="lead">
			<!-- Transactional data: changes on every follow-up, inline-editable with autosave. -->
			<section class="flex w-72 flex-none flex-col gap-5 overflow-y-auto border-r border-outline-gray-2 bg-surface-white p-4">
				<section>
					<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Status</div>
					<div class="flex flex-wrap items-center gap-2">
						<button
							v-for="s in LEAD_STATUSES"
							:key="s"
							type="button"
							class="rounded-full disabled:opacity-50"
							:class="status === s ? 'origin-center scale-[1.15] z-[1]' : 'opacity-70 hover:opacity-100'"
							:disabled="savingStatus"
							@click="status = s"
						>
							<Badge :label="s" :theme="leadStatusTheme(s)" size="sm" :variant="status === s ? 'solid' : 'subtle'" />
						</button>
					</div>
				</section>

				<section>
					<label class="mb-1.5 block text-xs text-ink-gray-5">Next Follow Up On</label>
					<input
						v-model="nextFollowUpLocal"
						type="datetime-local"
						class="form-input block h-8 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8"
					/>
				</section>

				<FormControl
					v-model="qualificationStatus"
					label="Qualification Status"
					type="select"
					size="sm"
					:options="qualificationOptions"
				/>

				<FormControl
					v-if="status === 'Do Not Contact'"
					v-model="statusComment"
					label="Status Comment"
					type="textarea"
					size="sm"
					placeholder="Reason for Do Not Contact (required)"
				/>

				<ErrorMessage :message="saveError" />

				<section class="space-y-2">
					<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Contact</div>
					<a
						v-for="number in phoneNumbers"
						:key="number"
						:href="`tel:${number}`"
						class="flex items-center gap-2 rounded-md border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 hover:bg-surface-gray-2"
						@click="showNoteDialog = true"
					>
						<FeatherIcon name="phone" class="h-4 w-4 flex-shrink-0 text-ink-gray-5" />
						<span>{{ number }}</span>
					</a>
					<a
						v-if="lead.email_id"
						:href="mailtoHref"
						class="flex items-center gap-2 rounded-md border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 hover:bg-surface-gray-2"
					>
						<FeatherIcon name="mail" class="h-4 w-4 flex-shrink-0 text-ink-gray-5" />
						<span class="truncate">{{ lead.email_id }}</span>
					</a>
				</section>

				<Button variant="subtle" @click="showNoteDialog = true">Add note</Button>
			</section>

			<!-- Master data: company/contact identity + firmographics. Rarely changes; read-only here. -->
			<section class="w-72 flex-none space-y-4 overflow-y-auto border-r border-outline-gray-2 bg-surface-white p-4 text-sm">
				<div>
					<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Company</div>
					<div class="text-ink-gray-8">{{ lead.company_name || "—" }}</div>
				</div>
				<div>
					<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Website</div>
					<div class="truncate text-ink-gray-8">{{ lead.website || "—" }}</div>
				</div>
				<div>
					<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Location</div>
					<div class="text-ink-gray-8">{{ locationLabel }}</div>
				</div>
				<div>
					<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Territory</div>
					<div class="text-ink-gray-8">{{ lead.territory || "—" }}</div>
				</div>
				<div>
					<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Source</div>
					<div class="text-ink-gray-8">{{ lead.source || "—" }}</div>
				</div>
				<div>
					<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Industry</div>
					<div class="text-ink-gray-8">{{ lead.industry || "—" }}</div>
				</div>
				<div>
					<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">No. of Employees</div>
					<div class="text-ink-gray-8">{{ lead.no_of_employees || "—" }}</div>
				</div>
				<div>
					<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Market Segment</div>
					<div class="text-ink-gray-8">{{ lead.market_segment || "—" }}</div>
				</div>
				<div>
					<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Annual Revenue</div>
					<div class="text-ink-gray-8">{{ lead.annual_revenue ?? "—" }}</div>
				</div>
				<div>
					<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Request Type</div>
					<div class="text-ink-gray-8">{{ lead.request_type || "—" }}</div>
				</div>
				<a
					:href="lead.desk_url"
					class="flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm font-medium text-ink-gray-7 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				>
					<FeatherIcon name="external-link" class="h-4 w-4 flex-shrink-0" />
					<span class="truncate">Open in Desk</span>
				</a>
			</section>

			<!-- Communication / Notes / Activities feed. -->
			<section class="flex min-w-0 flex-1 flex-col overflow-hidden bg-surface-gray-1">
				<div class="flex flex-shrink-0 items-center gap-2 border-b border-outline-gray-2 bg-surface-white px-4 py-2.5">
					<button
						v-for="tab in tabs"
						:key="tab.key"
						type="button"
						class="rounded-md px-2.5 py-1 text-sm font-medium"
						:class="
							activeTab === tab.key
								? 'bg-surface-gray-7 text-ink-white'
								: 'text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9'
						"
						@click="activeTab = tab.key"
					>
						{{ tab.label }}
					</button>
				</div>
				<div class="min-h-0 flex-1 overflow-y-auto p-4">
					<div v-if="activityLoading" class="flex items-center justify-center py-16 text-sm text-ink-gray-5">
						Loading…
					</div>
					<template v-else>
						<div v-if="activeTab === 'communications'">
							<div v-if="!communications.length" class="text-sm text-ink-gray-5">No communication logged yet.</div>
							<div v-else class="space-y-3">
								<div v-for="comm in communications" :key="comm.name" class="rounded-md border border-outline-gray-2 bg-surface-white px-3 py-2">
									<div class="mb-1 flex items-center gap-2 text-xs text-ink-gray-5">
										<Badge
											:label="comm.sent_or_received === 'Sent' ? 'Sent' : 'Received'"
											:theme="comm.sent_or_received === 'Sent' ? 'blue' : 'green'"
											size="sm"
											variant="subtle"
										/>
										<span>{{ formatDatetime(comm.communication_date) }}</span>
									</div>
									<div class="text-sm font-medium text-ink-gray-9">{{ comm.subject || "(no subject)" }}</div>
									<div class="mt-0.5 truncate text-xs text-ink-gray-6">{{ stripHtml(comm.content) }}</div>
								</div>
							</div>
						</div>

						<div v-else-if="activeTab === 'notes'">
							<div v-if="!notes.length" class="text-sm text-ink-gray-5">No notes yet.</div>
							<div v-else class="space-y-3">
								<div v-for="note in notes" :key="note.name" class="rounded-md border border-outline-gray-2 bg-surface-white px-3 py-2">
									<div class="mb-1 flex items-center gap-2 text-xs text-ink-gray-5">
										<span class="font-medium text-ink-gray-7">{{ note.added_by_name || note.added_by }}</span>
										<span>{{ formatDatetime(note.added_on) }}</span>
									</div>
									<div class="whitespace-pre-wrap text-sm text-ink-gray-8">{{ stripHtml(note.note) }}</div>
								</div>
							</div>
						</div>

						<div v-else>
							<div v-if="!activities.length" class="text-sm text-ink-gray-5">No activity recorded yet.</div>
							<div v-else class="space-y-3">
								<div v-for="(activity, index) in activities" :key="index" class="rounded-md border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm">
									<div class="mb-1 flex items-center gap-2 text-xs text-ink-gray-5">
										<span class="font-medium text-ink-gray-7">{{ activity.owner || "—" }}</span>
										<span>{{ formatDatetime(activity.creation) }}</span>
									</div>
									<div v-if="activity.kind === 'field_change'" class="text-ink-gray-8">
										Changed <span class="font-medium">{{ activity.label }}</span> from
										<span class="font-medium">{{ activity.old || "—" }}</span> to
										<span class="font-medium">{{ activity.new || "—" }}</span>
									</div>
									<div v-else class="text-ink-gray-8">{{ stripHtml(activity.content) }}</div>
								</div>
							</div>
						</div>
					</template>
				</div>
			</section>
		</template>
	</div>

	<Teleport v-if="chromeHostReady && lead" to="#cockpit-page-chrome">
		<div class="flex min-w-0 flex-1 items-center gap-3">
			<span class="truncate text-base font-bold tracking-tight text-ink-gray-9">
				{{ lead.lead_name || lead.name }}
			</span>
			<Badge :label="lead.status" :theme="leadStatusTheme(lead.status)" size="sm" variant="subtle" />
			<span class="ml-auto flex items-center gap-1.5 text-sm text-ink-gray-6">
				<span v-if="total" class="mr-1 tabular-nums">{{ position }} of {{ total }}</span>
				<button
					type="button"
					class="rounded p-1.5 hover:bg-surface-gray-2 disabled:opacity-40"
					:disabled="!hasPrevious"
					title="Previous"
					@click="emit('previous')"
				>
					<FeatherIcon name="chevron-left" class="h-4 w-4" />
				</button>
				<button
					type="button"
					class="rounded p-1.5 hover:bg-surface-gray-2 disabled:opacity-40"
					:disabled="!hasNext"
					title="Next"
					@click="emit('next')"
				>
					<FeatherIcon name="chevron-right" class="h-4 w-4" />
				</button>
				<button type="button" class="rounded p-1.5 hover:bg-surface-gray-2" title="Back to list" @click="emit('close')">
					<FeatherIcon name="x" class="h-4 w-4" />
				</button>
			</span>
		</div>
	</Teleport>

	<AddLeadNoteDialog v-if="lead" v-model="showNoteDialog" :lead="lead" @saved="onNoteSaved" />
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { call, debounce, toast, Badge } from "frappe-ui"
import {
	formatForApi,
	formatDatetime,
	parseDatetimeLocalValue,
	parseSystemDatetimeToUserDate,
	toDatetimeLocalValue,
} from "@spa/utils/datetime"
import { setPageChromeActive } from "@spa/pageChrome.js"
import { LEAD_STATUSES, QUALIFICATION_STATUSES, leadStatusTheme } from "@/leadListColumns.js"
import AddLeadNoteDialog from "./AddLeadNoteDialog.vue"

const API = "phamos.api.sales_leads"

const props = defineProps({
	name: { type: String, required: true },
	position: { type: Number, default: 0 },
	total: { type: Number, default: 0 },
})

const emit = defineEmits(["next", "previous", "close", "updated"])

const lead = ref(null)
const loading = ref(false)
const syncing = ref(false)
const savingStatus = ref(false)
const saveError = ref("")
const chromeHostReady = ref(false)
const showNoteDialog = ref(false)

const status = ref("")
const nextFollowUpLocal = ref("")
const qualificationStatus = ref("")
const statusComment = ref("")

const activityLoading = ref(false)
const notes = ref([])
const communications = ref([])
const activities = ref([])
const activeTab = ref("communications")

const tabs = [
	{ key: "communications", label: "Communication" },
	{ key: "notes", label: "Notes" },
	{ key: "activities", label: "Activities" },
]

const hasPrevious = computed(() => props.position > 1)
const hasNext = computed(() => props.position > 0 && props.position < props.total)

const qualificationOptions = computed(() => [
	{ label: "—", value: "" },
	...QUALIFICATION_STATUSES.map((q) => ({ label: q, value: q })),
])

const phoneNumbers = computed(() => [...new Set([lead.value?.mobile_no, lead.value?.phone].filter(Boolean))])

const mailtoHref = computed(() => {
	if (!lead.value) return ""
	const subject = encodeURIComponent(`Re: ${lead.value.lead_name || lead.value.company_name || lead.value.name}`)
	return `mailto:${lead.value.email_id}?cc=crm@phamos.eu&subject=${subject}`
})

const locationLabel = computed(() => {
	if (!lead.value) return "—"
	return [lead.value.city, lead.value.state, lead.value.country].filter(Boolean).join(", ") || "—"
})

function stripHtml(value) {
	return String(value || "")
		.replace(/<[^>]*>/g, " ")
		.replace(/\s+/g, " ")
		.trim()
}

function syncFieldsFromLead() {
	syncing.value = true
	status.value = lead.value.status || ""
	nextFollowUpLocal.value = toDatetimeLocalValue(parseSystemDatetimeToUserDate(lead.value.custom_next_followup))
	qualificationStatus.value = lead.value.qualification_status || ""
	statusComment.value = lead.value.custom_status_comment || ""
	saveError.value = ""
	nextTick(() => {
		syncing.value = false
	})
}

async function loadLead() {
	loading.value = true
	try {
		lead.value = await call(`${API}.get_lead`, { name: props.name })
		syncFieldsFromLead()
	} catch (e) {
		toast.error(e?.messages?.[0] || e?.message || "Could not load lead")
	} finally {
		loading.value = false
	}
}

async function loadActivity() {
	activityLoading.value = true
	try {
		const data = await call(`${API}.get_lead_activity`, { name: props.name })
		notes.value = data.notes || []
		communications.value = data.communications || []
		activities.value = data.activities || []
	} catch (e) {
		toast.error(e?.messages?.[0] || e?.message || "Could not load activity")
	} finally {
		activityLoading.value = false
	}
}

async function saveFields() {
	if (syncing.value || !lead.value) return
	saveError.value = ""
	savingStatus.value = true
	try {
		const updated = await call(`${API}.update_lead`, {
			name: lead.value.name,
			status: status.value,
			custom_next_followup: nextFollowUpLocal.value
				? formatForApi(parseDatetimeLocalValue(nextFollowUpLocal.value))
				: "",
			qualification_status: qualificationStatus.value,
			custom_status_comment: statusComment.value,
			if_modified: lead.value.modified,
		})
		if (updated.conflict) {
			toast.error("Saved — but this Lead was also changed by someone else just now. Check for lost edits.")
		}
		delete updated.conflict
		lead.value = updated
		syncFieldsFromLead()
		emit("updated", updated)
	} catch (e) {
		saveError.value = e?.messages?.[0] || e?.message || "Could not save lead"
		toast.error(saveError.value)
	} finally {
		savingStatus.value = false
	}
}

const scheduleSave = debounce(() => {
	saveFields()
}, 500)

watch([status, nextFollowUpLocal, qualificationStatus, statusComment], () => {
	if (syncing.value) return
	scheduleSave()
})

function onNoteSaved(updated) {
	lead.value = { ...lead.value, ...updated }
	syncFieldsFromLead()
	emit("updated", lead.value)
	loadActivity()
}

async function syncChromeHost() {
	await nextTick()
	chromeHostReady.value = !!document.getElementById("cockpit-page-chrome")
	if (chromeHostReady.value) setPageChromeActive(true)
}

function loadAll() {
	loadLead()
	loadActivity()
}

onMounted(() => {
	loadAll()
	syncChromeHost()
})

onBeforeUnmount(() => {
	setPageChromeActive(false)
})

watch(
	() => props.name,
	() => {
		activeTab.value = "communications"
		loadAll()
	}
)
</script>
