<template>
	<div class="flex h-full min-h-0 bg-surface-gray-1">
		<div class="h-full min-h-0 flex-1 overflow-y-auto p-5">
			<div class="mx-auto flex max-w-4xl flex-col gap-5">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div>
						<h1 class="text-lg font-semibold text-ink-gray-9">{{ __("My Leave") }}</h1>
						<p class="text-sm text-ink-gray-6">{{ __("Hand in leave here; your leave approver decides.") }}</p>
					</div>
					<Button variant="solid" :disabled="!hasEmployee" @click="openApply()">
						<template #prefix><FeatherIcon name="plus" class="h-4 w-4" /></template>
						{{ __("Apply for leave") }}
					</Button>
				</div>

				<div v-if="myLeave.error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
					{{ myLeave.error }}
				</div>
				<div v-else-if="!myLeave.loaded" class="flex min-h-64 items-center justify-center text-sm text-ink-gray-5">
					{{ __("Loading your leave…") }}
				</div>
				<p v-else-if="!hasEmployee" class="text-sm text-ink-gray-5">
					{{ __("Your user has no active Employee record, so there is no leave to show.") }}
				</p>
				<template v-else>
					<section v-if="balance.length" class="grid grid-cols-2 gap-3 md:grid-cols-4">
						<div
							v-for="row in balance"
							:key="row.leave_type"
							class="rounded-lg border border-outline-gray-2 bg-surface-white p-4"
						>
							<div class="truncate text-xs text-ink-gray-5" :title="__(row.leave_type)">{{ __(row.leave_type) }}</div>
							<div class="mt-1 text-2xl font-semibold tabular-nums text-ink-gray-9">{{ formatLeaveDays(row.remaining) }}</div>
							<div class="mt-1 text-xs text-ink-gray-5">
								{{
									__("{0} of {1} left · {2} pending", [
										formatLeaveDays(row.remaining),
										formatLeaveDays(row.allocated),
										formatLeaveDays(row.pending),
									])
								}}
							</div>
						</div>
					</section>
					<p v-else class="text-sm text-ink-gray-5">{{ __("No leave is allocated to you for today.") }}</p>

					<section class="rounded-lg border border-outline-gray-2 bg-surface-white">
						<div class="flex flex-wrap items-center justify-between gap-3 border-b border-outline-gray-1 px-4 py-3">
							<h2 class="text-sm font-semibold text-ink-gray-9">{{ __("Leave applications") }}</h2>
							<TabButtons v-model="statusFilter" :buttons="statusButtons" />
						</div>
						<p v-if="!rows.length" class="px-4 py-6 text-sm text-ink-gray-5">
							{{ statusFilter ? __("No leave with this status.") : __("You have not applied for leave yet.") }}
						</p>
						<ul v-else class="divide-y divide-outline-gray-1">
							<li v-for="row in rows" :key="row.name">
								<button
									type="button"
									class="flex w-full flex-wrap items-center justify-between gap-3 px-4 py-3 text-left hover:bg-surface-gray-1 focus:outline-none focus-visible:bg-surface-gray-2"
									:class="row.name === name ? 'bg-surface-gray-2' : ''"
									@click="select(row)"
								>
									<div class="min-w-0">
										<div class="text-sm font-medium text-ink-gray-9">{{ period(row) }}</div>
										<div class="mt-0.5 truncate text-xs text-ink-gray-6">
											{{ __(row.leave_type) }} · {{ __("{0} days", [formatLeaveDays(row.total_leave_days)]) }}
											<template v-if="row.cover_employee_name"> · {{ __("Covered by {0}", [row.cover_employee_name]) }}</template>
										</div>
									</div>
									<div class="flex items-center gap-2">
										<Badge v-if="badge(row)" :label="__(badge(row).key)" size="sm" variant="outline" :theme="badge(row).theme" :title="badge(row).title" />
										<Badge :label="statusLabel(row)" size="sm" variant="subtle" :theme="leaveStatusTheme(row.status)" />
									</div>
								</button>
							</li>
						</ul>
					</section>
				</template>
			</div>
		</div>

		<aside
			v-if="selected"
			class="h-full w-full max-w-sm shrink-0 overflow-y-auto border-l border-outline-gray-2 bg-surface-white p-5"
			:aria-label="__('Leave details')"
		>
			<div class="flex items-start justify-between gap-3">
				<div>
					<h2 class="text-base font-semibold text-ink-gray-9">{{ period(selected) }}</h2>
					<p class="mt-1 text-sm text-ink-gray-6">{{ __(selected.leave_type) }}</p>
				</div>
				<Button variant="ghost" :aria-label="__('Close')" @click="close">
					<FeatherIcon name="x" class="h-4 w-4" />
				</Button>
			</div>
			<div class="mt-3 flex flex-wrap gap-2">
				<Badge :label="statusLabel(selected)" size="sm" variant="subtle" :theme="leaveStatusTheme(selected.status)" />
				<Badge v-if="badge(selected)" :label="__(badge(selected).key)" size="sm" variant="outline" :theme="badge(selected).theme" />
			</div>
			<p v-if="selected.calendar?.state === 'error'" class="mt-2 text-xs text-ink-amber-3">{{ selected.calendar.error }}</p>
			<dl class="mt-4 space-y-3 text-sm">
				<div>
					<dt class="text-xs text-ink-gray-5">{{ __("Days") }}</dt>
					<dd class="text-ink-gray-9">
						{{ formatLeaveDays(selected.total_leave_days) }}
						<template v-if="selected.half_day">
							· {{ isSingleDay(selected) ? __("half day") : __("half day on {0}", [formatDate(selected.half_day_date)]) }}
						</template>
					</dd>
				</div>
				<div>
					<dt class="text-xs text-ink-gray-5">{{ __("Leave approver") }}</dt>
					<dd class="text-ink-gray-9">{{ selected.leave_approver_name || __("Not set") }}</dd>
				</div>
				<div>
					<dt class="text-xs text-ink-gray-5">{{ __("Covered by") }}</dt>
					<dd class="text-ink-gray-9">{{ selected.cover_employee_name || __("Nobody") }}</dd>
				</div>
				<div v-if="selected.description">
					<dt class="text-xs text-ink-gray-5">{{ __("Reason") }}</dt>
					<dd class="whitespace-pre-line text-ink-gray-9">{{ selected.description }}</dd>
				</div>
			</dl>
			<div class="mt-5 flex flex-wrap gap-2">
				<template v-if="selected.editable">
					<Button variant="subtle" @click="openApply(selected)">{{ __("Edit") }}</Button>
					<Button variant="subtle" theme="red" :loading="withdrawing" @click="withdraw(selected)">{{ __("Withdraw") }}</Button>
				</template>
				<Button variant="ghost" :link="deskRecordUrl('Leave Application', selected.name)" target="_blank">
					<template #prefix><FeatherIcon name="external-link" class="h-4 w-4" /></template>
					{{ __("Open in Desk") }}
				</Button>
			</div>
			<p v-if="!selected.editable" class="mt-3 text-xs text-ink-gray-5">
				{{ __("Decided leave can no longer be changed here. Ask HR if something needs to change.") }}
			</p>
		</aside>

		<ApplyLeaveDialog v-model="dialogOpen" :leave="editing" @saved="onSaved" />
	</div>
</template>

<script setup>
// My Leave in the Personal Cockpit (#1714): balance per leave type, all my leave applications
// newest first with a status filter, and a detail pane. Open leave can be edited and withdrawn;
// decided leave is read-only (decisions in the issue's grill, Q1–Q8).
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Badge, call, TabButtons } from "frappe-ui"
import { formatDate } from "@spa/utils/datetime.js"
import { deskRecordUrl } from "@spa/utils/deskUrl.js"
import { __ } from "@spa/utils/i18n.js"
import { notify } from "@spa/utils/notify.js"
import {
	calendarBadge,
	formatLeaveDays,
	isSingleDay,
	LEAVE_STATUSES,
	leaveStatusTheme,
} from "@spa/utils/leaveFormat.js"
import spaConfig from "@/config"
import ApplyLeaveDialog from "../components/ApplyLeaveDialog.vue"
import { loadMyLeave, loadMyLeaveBalance, myLeave } from "../leaveStore.js"

const props = defineProps({ name: { type: String, default: "" } })

const route = useRoute()
const router = useRouter()
const statusFilter = ref("")
const dialogOpen = ref(false)
const editing = ref(null)
const withdrawing = ref(false)

const hasEmployee = computed(() => Boolean(myLeave.data?.has_employee))
const balance = computed(() => myLeave.balance?.balance || [])
const allRows = computed(() => myLeave.data?.leave || [])
const rows = computed(() =>
	statusFilter.value ? allRows.value.filter((r) => r.status === statusFilter.value) : allRows.value
)
const selected = computed(() => allRows.value.find((r) => r.name === props.name) || null)

const statusButtons = computed(() => [
	{ label: __("All"), value: "" },
	...LEAVE_STATUSES.map((s) => ({ label: __(s), value: s })),
])

function period(row) {
	if (isSingleDay(row)) return formatDate(row.from_date)
	return `${formatDate(row.from_date)} – ${formatDate(row.to_date)}`
}

function statusLabel(row) {
	if (row.status === "Open" && row.leave_approver_name) return __("Waiting for {0}", [row.leave_approver_name])
	return __(row.status)
}

function badge(row) {
	return calendarBadge(row.calendar)
}

function select(row) {
	router.push({ name: "MyLeaveDetail", params: { name: row.name } })
}

function close() {
	router.push({ name: "MyLeave" })
}

function openApply(row = null) {
	editing.value = row
	dialogOpen.value = true
}

async function onSaved(doc) {
	notify.success(editing.value ? __("Leave saved") : __("Leave handed in"))
	await reload()
	if (doc?.name) router.push({ name: "MyLeaveDetail", params: { name: doc.name } })
}

async function withdraw(row) {
	if (!window.confirm(__("Withdraw this leave application? It is deleted and removed from your calendar."))) return
	withdrawing.value = true
	try {
		await call(`${spaConfig.api}.withdraw_leave`, { name: row.name })
		notify.success(__("Leave withdrawn"))
		await reload()
		close()
	} catch (e) {
		notify.error(__("Could not withdraw the leave"), e?.messages?.[0] || e?.message || "")
	} finally {
		withdrawing.value = false
	}
}

function reload() {
	return Promise.all([loadMyLeave(), loadMyLeaveBalance()])
}

// "Leave" in the Create menu arrives as ?new=1; open the dialog and drop the query, so a
// reload does not open it again.
function openFromQuery() {
	if (!route.query.new) return
	openApply()
	router.replace({ query: {} })
}

onMounted(() => {
	reload()
	openFromQuery()
})

// the same while the page is already shown
watch(() => route.query.new, openFromQuery)
</script>
