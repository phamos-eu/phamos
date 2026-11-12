<template>
	<Teleport v-if="lead && chromeHostReady" to="#cockpit-page-chrome">
		<div class="flex items-center gap-3">
			<span class="min-w-0 truncate text-base font-semibold tracking-tight text-ink-gray-9">
				{{ lead.lead_name || lead.name }}
			</span>
			<Badge
				v-if="lead.status"
				:label="leadStatusLabel(lead.status)"
				:theme="leadStatusTheme(lead.status)"
				size="sm"
				variant="subtle"
			/>
			<!-- Search and the note button live in the top bar rather than above the
			     stream: the bar is the page's own chrome and had room going spare. -->
			<FormControl
				v-model="feedSearch"
				type="text"
				size="sm"
				:placeholder="__('Search this lead…')"
				class="w-56 min-w-0"
			/>
			<Button variant="solid" size="sm" @click="showNoteDialog = true">
				<template #prefix><FeatherIcon name="plus" class="h-4 w-4" /></template>
				{{ __("Note") }}
			</Button>
			<button
				type="button"
				class="ml-1 rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				:title="__('Back to list')"
				@click="closeLead"
			>
				<FeatherIcon name="x" class="h-4 w-4" />
			</button>
		</div>
	</Teleport>

	<div class="flex h-full min-h-0 w-full flex-col">
		<div v-if="loading" class="flex flex-1 items-center justify-center text-sm text-ink-gray-5">{{ __("Loading…") }}</div>
		<template v-else-if="lead">
			<!-- Master data as a band across the top rather than a left column:
			     it is reference, not something worked in, and taking it out of the
			     columns gives the conversation the full width. -->
			<section class="flex-none border-b border-outline-gray-2 bg-surface-white px-4 py-3">
				<div class="grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-x-3 gap-y-2">
					<FormControl v-model="companyName" :label="__('Company')" type="text" size="sm" />

					<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">{{ __("Website") }}</label>
						<div class="flex items-center gap-1.5">
							<FormControl v-model="website" type="text" size="sm" placeholder="https://…" class="min-w-0 flex-1" />
							<button
								type="button"
								class="flex-shrink-0 rounded-md border border-outline-gray-2 p-1.5 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9 disabled:opacity-40"
								:disabled="!website || checkingWebsite"
								:title="__('Open website')"
								@click="openWebsite"
							>
								<FeatherIcon :name="checkingWebsite ? 'loader' : 'maximize-2'" class="h-4 w-4" />
							</button>
						</div>
					</div>

					<div class="grid grid-cols-2 gap-2">
						<FormControl v-model="city" :label="__('City')" type="text" size="sm" />
						<FormControl v-model="state" :label="__('State/Province')" type="text" size="sm" />
					</div>
					<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">{{ __("Country") }}</label>
						<FrappeLink doctype="Country" v-model="country" :placeholder="__('Country')" />
					</div>
					<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">{{ __("Territory") }}</label>
						<FrappeLink doctype="Territory" v-model="territory" :placeholder="__('Territory')" />
					</div>
					<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">{{ __("Source") }}</label>
						<FrappeLink doctype="Lead Source" v-model="source" :placeholder="__('Source')" />
					</div>
					<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">{{ __("Industry") }}</label>
						<FrappeLink doctype="Industry Type" v-model="industry" :placeholder="__('Industry')" />
					</div>
					<FormControl
						v-model="noOfEmployees"
						:label="__('No. of Employees')"
						type="select"
						size="sm"
						:options="noOfEmployeesOptions"
					/>
					<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">{{ __("Market Segment") }}</label>
						<FrappeLink doctype="Market Segment" v-model="marketSegment" :placeholder="__('Market Segment')" />
					</div>
					<FormControl v-model="annualRevenue" :label="__('Annual Revenue')" type="number" size="sm" />
					<FormControl
						v-model="requestType"
						:label="__('Request Type')"
						type="select"
						size="sm"
						:options="requestTypeOptions"
					/>
				</div>
			</section>

			<div class="flex min-h-0 flex-1">
				<!-- Communication / Notes / Activities feed: independent show/hide toggles,
				     not exclusive tabs, so any combination can be visible at once. -->
				<section class="flex min-w-0 flex-1 flex-col overflow-hidden bg-surface-gray-1">
					<div
						v-if="phoneNumbers.length || lead.email_id"
						class="flex flex-shrink-0 flex-wrap items-center gap-x-5 gap-y-1.5 border-b border-outline-gray-2 bg-surface-white px-4 py-3"
					>
						<!-- A call is the moment to write down what was said, so the
						     dialer link opens the note dialog alongside it. -->
						<a
							v-for="number in phoneNumbers"
							:key="number"
							:href="`tel:${number}`"
							class="flex items-center gap-1.5 text-sm text-ink-gray-7 hover:text-ink-gray-9"
							@click="showNoteDialog = true"
						>
							<FeatherIcon name="phone" class="h-3.5 w-3.5 flex-shrink-0 text-ink-gray-5" />
							<span>{{ number }}</span>
						</a>
						<!-- Sending from the cockpit is #1860; until then the mail client does it. -->
						<a
							v-if="lead.email_id"
							:href="`mailto:${lead.email_id}`"
							class="flex items-center gap-1.5 text-sm text-ink-gray-7 hover:text-ink-gray-9"
							:title="__('Write an email')"
						>
							<FeatherIcon name="mail" class="h-3.5 w-3.5 flex-shrink-0 text-ink-gray-5" />
							<span class="truncate">{{ lead.email_id }}</span>
						</a>
					</div>
					<div class="max-h-[33%] flex-shrink-0 overflow-y-auto border-b border-outline-gray-2 bg-surface-white px-4 py-2.5">
						<label class="mb-1.5 flex items-center gap-1.5 text-xs text-ink-gray-5">
							<span>{{ __("Status Comment") }}</span>
							<!-- Conditionally mandatory on the doctype itself (mandatory_depends_on
							     eval:doc.status=='Do Not Contact'), so flag it rather than let the
							     save fail with a bare validation error. -->
							<span v-if="status === 'Do Not Contact'" class="text-ink-red-4">{{ __("required") }}</span>
							<span v-if="statusCommentStamp" class="ml-auto truncate text-ink-gray-5">
								{{ statusCommentStamp }}
							</span>
						</label>
						<!-- Grows with its content instead of hiding the rest behind a
						     two-line scroll: a status comment is the one thing on this
						     record people write paragraphs in. -->
						<textarea
							ref="statusCommentEl"
							v-model="statusComment"
							rows="2"
							:placeholder="__('Reason and comments for this lead\'s status')"
							class="form-textarea block max-h-40 w-full resize-none overflow-y-auto rounded border border-outline-gray-2 bg-surface-white px-2 py-1.5 text-base text-ink-gray-8"
							@input="autoGrowStatusComment"
						/>
					</div>
					<div class="flex flex-shrink-0 items-center gap-2 border-b border-outline-gray-2 bg-surface-white px-4 py-2.5">
						<!-- Icon + colour per type, matching the entries below, so the row
						     doubles as the stream's legend. -->
						<button
							v-for="filter in feedFilters"
							:key="filter.key"
							type="button"
							class="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm font-medium"
							:class="activeFilters.has(filter.key) ? filter.on : filter.off"
							:aria-pressed="activeFilters.has(filter.key)"
							@click="toggleFilter(filter.key)"
						>
							<FeatherIcon :name="filter.icon" class="h-3.5 w-3.5 flex-none" />
							<span>{{ __(filter.label) }}</span>
						</button>
					</div>
					<div class="min-h-0 flex-1 overflow-y-auto p-4">
						<div v-if="activityLoading" class="flex items-center justify-center py-16 text-sm text-ink-gray-5">
							{{ __("Loading…") }}
						</div>
						<div v-else-if="!activeFilters.size" class="flex items-center justify-center py-16 text-sm text-ink-gray-5">
							{{ __("Select Communication, Notes, or Activities to view.") }}
						</div>
						<div v-else-if="!timeline.length" class="flex items-center justify-center py-16 text-sm text-ink-gray-5">
							{{ feedSearch.trim() ? __("Nothing here matches that search.") : __("Nothing recorded yet.") }}
						</div>
						<!-- One chronological stream: the toggles above filter which entry types appear in it. -->
						<div v-else class="space-y-2">
							<template v-for="entry in timeline" :key="entry.key">
								<!--
									Follows the Desk timeline's split: emails and notes are cards
									with an icon; version/system entries are plain muted lines,
									so "what happened to the record" never competes with "what was
									said to the customer". Columnar so a run of changes scans down
									the page rather than as sentences of differing length.
								-->
								<div
									v-if="entry.type === 'activities'"
									class="grid grid-cols-[0.9rem_minmax(0,1fr)_minmax(0,1.5fr)_minmax(0,0.9fr)_auto] items-baseline gap-x-3 px-1 py-1 text-xs text-ink-gray-6"
								>
									<FeatherIcon name="git-commit" class="h-3.5 w-3.5 flex-none translate-y-0.5 text-ink-gray-4" />
									<span class="truncate font-medium text-ink-gray-7">{{ activityLabel(entry) }}</span>
									<span class="truncate">{{ activityDetail(entry) }}</span>
									<span class="truncate text-ink-gray-5">{{ entry.author }}</span>
									<span class="whitespace-nowrap tabular-nums text-ink-gray-5">
										{{ formatDatetime(entry.date) }}
									</span>
								</div>

								<div
									v-else
									class="rounded-md border border-l-2 border-outline-gray-2 bg-surface-white px-3 py-2.5"
									:class="entryType(entry).accent"
								>
									<div class="mb-1.5 flex items-center gap-2 text-xs text-ink-gray-5">
										<FeatherIcon
											:name="entryType(entry).icon"
											class="h-3.5 w-3.5 flex-none"
											:class="entryType(entry).iconColor"
										/>
										<Badge :label="__(entry.badge)" :theme="entry.badgeTheme" size="sm" variant="subtle" />
										<span v-if="entry.author" class="min-w-0 truncate font-medium text-ink-gray-7">
											{{ entry.author }}
										</span>
										<span class="whitespace-nowrap">{{ formatDatetime(entry.date) }}</span>
										<button
											v-if="entry.threadSize > 1"
											type="button"
											class="flex flex-none items-center gap-1 rounded bg-blue-50 px-1.5 py-0.5 text-xs font-medium text-blue-700 hover:bg-blue-100 dark:bg-blue-900 dark:text-blue-300"
											:aria-expanded="openThreads.has(entry.threadKey)"
											@click="toggleThread(entry.threadKey)"
										>
											<FeatherIcon
												:name="openThreads.has(entry.threadKey) ? 'chevron-down' : 'chevron-right'"
												class="h-3 w-3"
											/>
											<span>{{ __("{0} messages", [entry.threadSize]) }}</span>
										</button>
										<button
											v-if="entry.type === 'notes'"
											type="button"
											:title="__('Edit note')"
											class="ml-auto flex-none rounded p-1 text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
											@click="openNoteEditor(entry)"
										>
											<FeatherIcon name="edit-2" class="h-3.5 w-3.5" />
										</button>
									</div>

									<template v-if="entry.type === 'communications'">
										<div class="text-sm font-medium text-ink-gray-9">{{ entry.subject || __("(no subject)") }}</div>

										<!-- Folded: the latest message, rendered as it was written and
										     given real room: enough to read rather than guess at. -->
										<template v-if="!openThreads.has(entry.threadKey)">
											<div v-if="entry.recipients" class="mt-0.5 truncate text-xs text-ink-gray-5">
												{{ __("to {0}", [entry.recipients]) }}
											</div>
											<EmailBody class="mt-1.5" :html="entry.communication.content_html" />
											<button
												v-if="entry.threadSize > 1"
												type="button"
												class="mt-1 text-xs font-medium text-blue-700 hover:underline dark:text-blue-400"
												@click="toggleThread(entry.threadKey)"
											>
												{{
													entry.threadSize === 2
														? __("Show 1 earlier message")
														: __("Show {0} earlier messages", [entry.threadSize - 1])
												}}
											</button>
										</template>

										<!-- Unfolded: every message in the conversation, newest first. -->
										<div v-else class="mt-2 space-y-2">
											<div
												v-for="message in entry.messages"
												:key="message.name"
												class="rounded border border-outline-gray-2 px-2.5 py-2"
											>
												<div class="mb-1 flex flex-wrap items-center gap-2 text-xs text-ink-gray-5">
													<Badge
														:label="message.sent_or_received === 'Sent' ? __('Sent') : __('Received')"
														:theme="message.sent_or_received === 'Sent' ? 'blue' : 'green'"
														size="sm"
														variant="subtle"
													/>
													<span class="min-w-0 truncate font-medium text-ink-gray-7">{{ message.sender }}</span>
													<span class="whitespace-nowrap">{{ formatDatetime(message.communication_date) }}</span>
												</div>
												<div v-if="message.recipients" class="mb-1 truncate text-xs text-ink-gray-5">
													{{ __("to {0}", [message.recipients]) }}
												</div>
												<EmailBody :html="message.content_html" max-height-class="max-h-[22vh]" />
											</div>
										</div>
									</template>

									<div v-else class="whitespace-pre-wrap text-sm text-ink-gray-8">{{ entry.body }}</div>
								</div>
							</template>
						</div>
					</div>
				</section>

				<!-- Transactional data: changes on every follow-up, inline-editable with autosave. -->
				<section class="flex w-72 flex-none flex-col gap-5 overflow-y-auto border-l border-outline-gray-2 bg-surface-white p-4">
					<section>
						<div class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
							{{ __("Status") }}
						</div>
						<div class="flex flex-wrap items-center gap-2">
							<button
								v-for="s in LEAD_STATUSES"
								:key="s"
								type="button"
								class="rounded-full disabled:opacity-50"
								:class="status === s ? 'z-[1] origin-center scale-[1.15]' : 'opacity-70 hover:opacity-100'"
								:disabled="savingStatus"
								@click="status = s"
							>
								<!-- Drawn by hand when selected: frappe-ui's solid orange Badge puts
								     near-white text on light amber, so "Opportunity" read as blank. -->
								<span
									v-if="status === s"
									class="inline-flex h-5 items-center whitespace-nowrap rounded-full px-1.5 text-xs font-semibold"
									:class="leadStatusStrongClass(s)"
								>
									{{ leadStatusLabel(s) }}
								</span>
								<Badge v-else :label="leadStatusLabel(s)" :theme="leadStatusTheme(s)" size="sm" variant="subtle" />
							</button>
						</div>
					</section>

					<section>
						<label class="mb-1.5 block text-xs text-ink-gray-5">{{ __("Next Follow Up On") }}</label>
						<input
							v-model="nextFollowUp"
							type="date"
							class="form-input block h-8 w-full rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8"
						/>
					</section>

					<div>
						<label class="mb-1.5 block text-xs text-ink-gray-5">{{ __("Lead Owner") }}</label>
						<FrappeLink doctype="User" v-model="leadOwner" :placeholder="__('Lead Owner')" />
					</div>

					<FormControl
						v-model="qualificationStatus"
						:label="__('Qualification Status')"
						type="select"
						size="sm"
						:options="qualificationOptions"
					/>

					<ErrorMessage :message="saveError" />

					<a
						:href="lead.desk_url"
						class="mt-auto flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm font-medium text-ink-gray-7 hover:bg-surface-gray-2 hover:text-ink-gray-9"
					>
						<FeatherIcon name="external-link" class="h-4 w-4 flex-shrink-0" />
						<span class="truncate">{{ __("Open in Desk") }}</span>
					</a>
				</section>
			</div>
		</template>
	</div>

	<AddLeadNoteDialog v-if="lead" v-model="showNoteDialog" :lead="lead" @saved="onNoteSaved" />

	<EditLeadNoteDialog
		v-if="lead && editingNote"
		v-model="showEditNoteDialog"
		:lead="lead"
		:note="editingNote"
		@saved="onNoteEdited"
	/>

	<Dialog
		v-model="showWebsiteDialog"
		:options="{ title: lead?.company_name || lead?.lead_name || __('Website'), size: '5xl' }"
	>
		<template #body-content>
			<!-- A lead's website is attacker-supplied whenever leads arrive from a
			     web form, and passing the embeddability check says only that the
			     site allows framing, not that it behaves. Sandboxed without
			     allow-top-navigation so it cannot replace the cockpit. -->
			<iframe
				:src="websiteDialogUrl"
				sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
				referrerpolicy="no-referrer"
				class="h-[70vh] w-full rounded-md border border-outline-gray-2"
			/>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { call, toast, Badge } from "frappe-ui"
import { formatDate, formatDatetime } from "@spa/utils/datetime"
import { setPageChromeActive } from "@spa/pageChrome.js"
import { __ } from "@spa/utils/i18n.js"
import {
	LEAD_STATUSES,
	NO_OF_EMPLOYEES_OPTIONS,
	QUALIFICATION_STATUSES,
	REQUEST_TYPE_OPTIONS,
	leadStatusLabel,
	leadStatusStrongClass,
	leadStatusTheme,
} from "@/leadListColumns.js"
import FrappeLink from "@spa/components/FrappeLink.vue"
import AddLeadNoteDialog from "./AddLeadNoteDialog.vue"
import EditLeadNoteDialog from "./EditLeadNoteDialog.vue"
import EmailBody from "./EmailBody.vue"

const API = "phamos.api.sales_leads"

const props = defineProps({
	name: { type: String, required: true },
})

const emit = defineEmits(["close", "updated"])

const lead = ref(null)
const loading = ref(false)
const syncing = ref(false)
const savingStatus = ref(false)
const saveError = ref("")
const showNoteDialog = ref(false)
const showEditNoteDialog = ref(false)
const editingNote = ref(null)
const showWebsiteDialog = ref(false)
const checkingWebsite = ref(false)
const feedSearch = ref("")
const chromeHostReady = ref(false)

const status = ref("")
// Date-only (YYYY-MM-DD), bound straight to an <input type="date">: no
// timezone conversion, which would shift a bare date across day boundaries.
const nextFollowUp = ref("")
const qualificationStatus = ref("")
const statusComment = ref("")
const statusCommentEl = ref(null)
const leadOwner = ref("")

const companyName = ref("")
const website = ref("")
const city = ref("")
const state = ref("")
const country = ref("")
const territory = ref("")
const source = ref("")
const industry = ref("")
const noOfEmployees = ref("")
const marketSegment = ref("")
const annualRevenue = ref("")
const requestType = ref("")

const activityLoading = ref(false)
const notes = ref([])
const communications = ref([])
const activities = ref([])
// Independent show/hide toggles (not exclusive tabs): any combination can be
// visible together.
const activeFilters = ref(new Set(["communications", "notes", "activities"]))

const statusCommentStamp = computed(() => {
	const who = lead.value?.custom_status_comment_modified_by_name
	const when = lead.value?.custom_status_comment_modified_date
	if (!who && !when) return ""
	return [who, when ? formatDate(String(when).slice(0, 10)) : ""].filter(Boolean).join(" · ")
})

/** A comment shows all of itself, up to the field's own max height. */
function autoGrowStatusComment() {
	const el = statusCommentEl.value
	if (!el) return
	el.style.height = "auto"
	el.style.height = `${el.scrollHeight}px`
}

/**
 * Each entry type owns an icon and a colour, used identically on the filter
 * chip and on the entries themselves, so the toggle reads as a legend for the
 * stream below it.
 */
const FEED_TYPES = {
	communications: {
		label: "Communication",
		icon: "mail",
		on: "bg-blue-600 text-white",
		off: "text-blue-700 hover:bg-blue-50 dark:text-blue-400",
		accent: "border-l-blue-500",
		iconColor: "text-blue-600",
	},
	notes: {
		label: "Notes",
		icon: "message-square",
		on: "bg-amber-600 text-white",
		off: "text-amber-700 hover:bg-amber-50 dark:text-amber-400",
		accent: "border-l-amber-500",
		iconColor: "text-amber-600",
	},
	activities: {
		label: "Activities",
		icon: "git-commit",
		on: "bg-gray-700 text-white",
		off: "text-ink-gray-6 hover:bg-surface-gray-2",
		accent: "border-l-gray-400",
		iconColor: "text-ink-gray-5",
	},
}

const feedFilters = Object.entries(FEED_TYPES).map(([key, type]) => ({ key, ...type }))

/** Threads the user has opened, by thread key. */
const openThreads = ref(new Set())

function toggleThread(key) {
	const next = new Set(openThreads.value)
	if (next.has(key)) next.delete(key)
	else next.add(key)
	openThreads.value = next
}

function toggleFilter(key) {
	const next = new Set(activeFilters.value)
	if (next.has(key)) next.delete(key)
	else next.add(key)
	activeFilters.value = next
}

/** Communications, notes and activities merged into one chronological stream. */
const timeline = computed(() => {
	const entries = []

	if (activeFilters.value.has("communications")) {
		// One entry per conversation, not per message: a thread is the unit
		// people think in, and stacking it keeps a long back-and-forth from
		// burying everything else in the stream.
		const threads = new Map()
		for (const comm of communications.value) {
			const key = comm.thread_key || comm.name
			if (!threads.has(key)) threads.set(key, [])
			threads.get(key).push(comm)
		}

		for (const [key, messages] of threads) {
			// Backend returns newest first; keep that order inside the thread.
			const latest = messages[0]
			entries.push({
				key: `thread:${key}`,
				type: "communications",
				date: latest.communication_date,
				badge: latest.sent_or_received === "Sent" ? "Sent" : "Received",
				badgeTheme: latest.sent_or_received === "Sent" ? "blue" : "green",
				author: latest.sender,
				recipients: latest.recipients,
				subject: latest.subject,
				threadSize: messages.length,
				threadKey: key,
				messages,
				communication: latest,
			})
		}
	}

	if (activeFilters.value.has("notes")) {
		for (const note of notes.value) {
			entries.push({
				key: `note:${note.name}`,
				type: "notes",
				date: note.added_on,
				badge: "Note",
				badgeTheme: "orange",
				author: note.added_by_name || note.added_by,
				body: stripHtml(note.note),
				note,
			})
		}
	}

	if (activeFilters.value.has("activities")) {
		activities.value.forEach((activity, index) => {
			entries.push({
				key: `activity:${index}`,
				type: "activities",
				date: activity.creation,
				author: activity.owner_name || activity.owner,
				activity,
				fieldChange: activity.kind === "field_change" ? activity : null,
				body: stripHtml(activity.content),
			})
		})
	}

	const sorted = entries.sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")))

	const query = feedSearch.value.trim().toLowerCase()
	if (!query) return sorted

	return sorted.filter((entry) => {
		const haystack = [
			entry.subject,
			entry.author,
			entry.body,
			entry.recipients,
			// Emails render from HTML, so search the text of every message in the thread.
			...(entry.messages || []).map((m) => `${m.subject} ${m.sender} ${stripHtml(m.content)}`),
			entry.activity ? `${activityLabel(entry)} ${activityDetail(entry)}` : "",
		]
			.filter(Boolean)
			.join(" ")
			.toLowerCase()
		return haystack.includes(query)
	})
})

/** Stored values stay English; only the label is translated. */
function selectOptions(values) {
	return [{ label: "—", value: "" }, ...values.map((v) => ({ label: __(v), value: v }))]
}

const qualificationOptions = computed(() => selectOptions(QUALIFICATION_STATUSES))
const noOfEmployeesOptions = computed(() => selectOptions(NO_OF_EMPLOYEES_OPTIONS))
const requestTypeOptions = computed(() => selectOptions(REQUEST_TYPE_OPTIONS))

const phoneNumbers = computed(() => [
	...new Set([lead.value?.mobile_no, lead.value?.phone].filter(Boolean)),
])

/** Left column: what was touched. */
function activityLabel(entry) {
	return entry.activity?.label || entry.fieldChange?.label || __("Record updated")
}

/** Middle column: what changed about it. */
function activityDetail(entry) {
	const activity = entry.activity
	if (activity?.kind === "row_added") return __("Added: {0}", [activity.summary || "—"])
	if (activity?.kind === "row_removed") return __("Removed: {0}", [activity.summary || "—"])
	if (entry.fieldChange) return `${entry.fieldChange.old || "—"} → ${entry.fieldChange.new || "—"}`
	return entry.body || ""
}

function entryType(entry) {
	return FEED_TYPES[entry.type] || FEED_TYPES.activities
}

function errorText(e, fallback) {
	return e?.messages?.[0] || e?.message || fallback
}

function toastError(message) {
	toast({ title: message, icon: "x-circle", iconClasses: "text-ink-red-4" })
}

// Resolved server-side by check_website_embeddable (normalized + redirects
// followed), set only once we know the site will actually render framed.
const websiteDialogUrl = ref("")

async function openWebsite() {
	if (!website.value || checkingWebsite.value) return
	checkingWebsite.value = true
	try {
		const result = await call(`${API}.check_website_embeddable`, { url: website.value })
		if (result.embeddable) {
			websiteDialogUrl.value = result.url
			showWebsiteDialog.value = true
			return
		}
		// Can't be framed (or didn't respond): open a tab instead of showing a blank dialog.
		window.open(result.url, "_blank", "noopener")
		toast({
			title:
				result.reason === "blocked"
					? __("This site blocks embedding, so it opened in a new tab.")
					: __("Could not reach this site to preview it, so it opened in a new tab."),
			icon: "alert-triangle",
			iconClasses: "text-ink-amber-3",
		})
	} catch (e) {
		toastError(errorText(e, __("Could not open website")))
	} finally {
		checkingWebsite.value = false
	}
}

function stripHtml(value) {
	return String(value || "")
		.replace(/<[^>]*>/g, " ")
		.replace(/\s+/g, " ")
		.trim()
}

/**
 * Editable fields and the refs bound to them. `baseline` holds what the server
 * last said for each, so a save sends only what the user actually changed and
 * never writes a stale value back over someone else's edit.
 */
const FIELD_REFS = {
	status,
	custom_next_followup: nextFollowUp,
	qualification_status: qualificationStatus,
	custom_status_comment: statusComment,
	lead_owner: leadOwner,
	company_name: companyName,
	website,
	city,
	state,
	country,
	territory,
	source,
	industry,
	no_of_employees: noOfEmployees,
	market_segment: marketSegment,
	annual_revenue: annualRevenue,
	request_type: requestType,
}
let baseline = {}

/** The server value as the form shows it ("" for empty). */
function formValue(doc, field) {
	if (field === "annual_revenue") return doc.annual_revenue ?? ""
	return doc[field] || ""
}

/** Set refs without triggering an autosave. */
function setQuietly(apply) {
	syncing.value = true
	apply()
	nextTick(() => {
		syncing.value = false
	})
}

function syncFieldsFromLead() {
	setQuietly(() => {
		for (const [field, fieldRef] of Object.entries(FIELD_REFS)) {
			fieldRef.value = formValue(lead.value, field)
		}
	})
	baseline = Object.fromEntries(Object.keys(FIELD_REFS).map((f) => [f, formValue(lead.value, f)]))
	// Size the box to a stored comment on arrival, not after the first keystroke.
	nextTick(autoGrowStatusComment)
	saveError.value = ""
}

async function loadLead() {
	loading.value = true
	try {
		lead.value = await call(`${API}.get_lead`, { name: props.name })
		syncFieldsFromLead()
	} catch (e) {
		toastError(errorText(e, __("Could not load lead")))
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
		toastError(errorText(e, __("Could not load activity")))
	} finally {
		activityLoading.value = false
	}
}

let saveTimer = null
let inFlight = null
let saveAgain = false

/** One save at a time; edits made meanwhile go out in one more save after it,
 *  carrying the `modified` that save returned (else: false conflict warnings). */
function saveFields() {
	if (inFlight) {
		saveAgain = true
		return inFlight
	}
	inFlight = sendChanges().finally(() => {
		inFlight = null
		if (saveAgain) {
			saveAgain = false
			return saveFields()
		}
	})
	return inFlight
}

async function sendChanges() {
	if (!lead.value) return
	const changes = {}
	for (const [field, fieldRef] of Object.entries(FIELD_REFS)) {
		if (fieldRef.value !== baseline[field]) changes[field] = fieldRef.value
	}
	if (!Object.keys(changes).length) return

	const payload = { ...changes }
	if (payload.annual_revenue === "") payload.annual_revenue = 0
	saveError.value = ""
	savingStatus.value = true
	try {
		const updated = await call(`${API}.update_lead`, {
			name: lead.value.name,
			...payload,
			if_modified: lead.value.modified,
		})
		if (updated.conflict) {
			toast({
				title: __("Saved, but someone else changed this lead just now. Check for lost edits."),
				icon: "alert-triangle",
				iconClasses: "text-ink-amber-3",
			})
		}
		delete updated.conflict
		if (updated.name !== lead.value.name) return

		// What was sent is now the server's value, unless the server changed it.
		for (const field of Object.keys(changes)) baseline[field] = changes[field]

		// ERPNext derives some statuses (Opportunity, Quotation, Converted…)
		// from linked records and overrides a manual choice on save. Show what
		// was kept rather than the choice that didn't stick, unless the user
		// has already picked another status while the save was in flight.
		if ("status" in changes && updated.status !== changes.status && status.value === changes.status) {
			setQuietly(() => (status.value = updated.status))
			toast({
				title: __("ERPNext kept the status at {0}: it follows linked opportunities, quotations and customers.", [
					leadStatusLabel(updated.status),
				]),
				icon: "info",
				iconClasses: "text-ink-blue-3",
			})
		}

		// Fields the user hasn't touched take the server's value, so someone
		// else's change shows up. Touched ones keep what is being typed: the
		// next save sends them.
		setQuietly(() => {
			for (const [field, fieldRef] of Object.entries(FIELD_REFS)) {
				const serverValue = formValue(updated, field)
				if (fieldRef.value === baseline[field]) fieldRef.value = serverValue
				baseline[field] = serverValue
			}
		})
		lead.value = updated
		emit("updated", updated)
	} catch (e) {
		saveError.value = errorText(e, __("Could not save lead"))
		toastError(saveError.value)
	} finally {
		savingStatus.value = false
	}
}

function scheduleSave() {
	clearTimeout(saveTimer)
	saveTimer = setTimeout(() => {
		saveTimer = null
		saveFields()
	}, 500)
}

/** Send a pending edit now: before switching leads or leaving the record. */
function flushSave() {
	if (saveTimer) {
		clearTimeout(saveTimer)
		saveTimer = null
		return saveFields()
	}
	return inFlight || Promise.resolve()
}

async function closeLead() {
	await flushSave()
	emit("close")
}

watch(Object.values(FIELD_REFS), () => {
	if (syncing.value) return
	scheduleSave()
})

function openNoteEditor(entry) {
	editingNote.value = entry.note
	showEditNoteDialog.value = true
}

function onNoteEdited(savedNotes) {
	notes.value = savedNotes || []
}

function onNoteSaved(updated) {
	lead.value = { ...lead.value, ...updated }
	syncFieldsFromLead()
	emit("updated", lead.value)
	loadActivity()
}

function loadAll() {
	loadLead()
	loadActivity()
}

onMounted(() => {
	chromeHostReady.value = !!document.getElementById("cockpit-page-chrome")
	if (chromeHostReady.value) setPageChromeActive(true)
	loadAll()
})

onBeforeUnmount(() => {
	flushSave()
	setPageChromeActive(false)
})

watch(
	() => props.name,
	async () => {
		// Still the previous lead's fields: save them to that lead first.
		await flushSave()
		loadAll()
	}
)
</script>
