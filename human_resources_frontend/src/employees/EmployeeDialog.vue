<template>
	<Dialog
		:model-value="modelValue"
		:options="{ title: detail?.employee_name || employeeName || 'Employee', size: '2xl' }"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div v-if="error" class="rounded-lg border border-outline-gray-2 bg-surface-red-1 p-4 text-sm text-ink-red-4">
				{{ error }}
			</div>
			<div v-else-if="!detail" class="flex min-h-40 items-center justify-center text-sm text-ink-gray-5">Loading…</div>
			<div v-else class="space-y-5">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div class="min-w-0">
						<p v-if="detail.department || detail.designation" class="truncate text-sm text-ink-gray-6">
							{{ [detail.department, detail.designation].filter(Boolean).join(" · ") }}
						</p>
						<p class="text-xs text-ink-gray-5">{{ detail.employee }} · {{ detail.company }}</p>
					</div>
					<Badge :label="detail.status" size="sm" variant="subtle" :theme="detail.status === 'Active' ? 'green' : 'gray'" />
				</div>

				<!-- Key facts. Sick days and the contract come only for the roles allowed to see them (#1833). -->
				<dl class="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
					<div v-for="fact in facts" :key="fact.label">
						<dt class="text-xs text-ink-gray-5">{{ fact.label }}</dt>
						<dd class="mt-0.5 tabular-nums text-ink-gray-9" :class="fact.muted ? 'text-ink-gray-5' : ''">{{ fact.value }}</dd>
					</div>
				</dl>

				<section>
					<h3 class="mb-2 text-xs font-medium uppercase tracking-wide text-ink-gray-5">Leave this year</h3>
					<p v-if="!balance.length" class="text-sm text-ink-gray-5">No leave is allocated this year.</p>
					<table v-else class="w-full text-sm">
						<thead class="text-xs text-ink-gray-5">
							<tr>
								<th class="py-1 text-left font-medium">Type</th>
								<th class="py-1 text-right font-medium">Left</th>
								<th class="py-1 text-right font-medium">Taken</th>
								<th class="py-1 text-right font-medium">Allocated</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="row in balance" :key="row.leave_type" class="border-t border-outline-gray-1">
								<td class="py-1.5 text-ink-gray-8">{{ row.leave_type }}</td>
								<td class="py-1.5 text-right font-medium tabular-nums text-ink-gray-9">{{ formatNumber(row.left) }}</td>
								<td class="py-1.5 text-right tabular-nums text-ink-gray-8">{{ formatNumber(row.taken) }}</td>
								<td class="py-1.5 text-right tabular-nums text-ink-gray-8">{{ formatNumber(row.allocated) }}</td>
							</tr>
						</tbody>
					</table>
				</section>

				<section>
					<h3 class="mb-2 text-xs font-medium uppercase tracking-wide text-ink-gray-5">Leave days {{ year }}</h3>
					<LeaveHeatmap :year="year" :applications="detail.applications" :holidays="detail.holidays" />
					<p v-if="detail.can_see_sick_days" class="mt-2 text-xs text-ink-gray-5">Sick leave is not drawn; only HR Manager sees its count above.</p>
				</section>

				<div class="flex flex-wrap items-center gap-4 border-t border-outline-gray-1 pt-4 text-sm">
					<a :href="deskUrl('Employee', detail.employee)" target="_blank" rel="noopener" class="inline-flex items-center gap-1.5 text-ink-gray-7 hover:text-ink-gray-9">
						<FeatherIcon name="external-link" class="h-4 w-4" /> Open in Desk
					</a>
					<RouterLink
						v-if="detail.contract"
						:to="{ name: 'ContractDetail', params: { name: detail.contract.name } }"
						class="inline-flex items-center gap-1.5 text-ink-gray-7 hover:text-ink-gray-9"
						@click="emit('update:modelValue', false)"
					>
						<FeatherIcon name="file-text" class="h-4 w-4" /> Open contract
					</RouterLink>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { Badge, call, Dialog } from "frappe-ui"
import { errorMessage, formatDate, formatNumber, formatPercent } from "@spa/contracts/contractFormat.js"
import { getDateFormat } from "@spa/utils/datetime.js"
import LeaveHeatmap from "./LeaveHeatmap.vue"

const year = new Date().getFullYear()

// One employee's leave and HR facts (#1836). The API applies the access rules of #1833:
// no sick days and no contract for HR User, and never a sick leave among the applications.
const props = defineProps({
	modelValue: { type: Boolean, default: false },
	employee: { type: String, default: "" },
	employeeName: { type: String, default: "" },
})
const emit = defineEmits(["update:modelValue"])

const detail = ref(null)
const error = ref("")

watch(
	() => [props.modelValue, props.employee],
	async ([open, employee]) => {
		if (!open || !employee) return
		detail.value = null
		error.value = ""
		try {
			detail.value = await call("phamos.api.hr_employees.get_employee", { name: employee })
		} catch (e) {
			error.value = errorMessage(e, "Could not load the employee")
		}
	},
	{ immediate: true }
)

const balance = computed(() =>
	Object.entries(detail.value?.leave || {}).map(([leave_type, v]) => ({ leave_type, ...v }))
)

const facts = computed(() => {
	const d = detail.value
	const list = [
		{ label: "Years in company", value: d.years_in_company == null ? "—" : formatNumber(d.years_in_company) },
		{ label: "Birthday", value: d.birthday ? formatBirthday(d.birthday) : "—", muted: !d.birthday },
		{ label: "Last leave", value: formatDate(d.last_leave) || "—", muted: !d.last_leave },
		{ label: "Next leave", value: formatDate(d.next_leave) || "—", muted: !d.next_leave },
		{ label: "Requests waiting", value: d.pending_count || "—", muted: !d.pending_count },
	]
	if (d.can_see_sick_days) {
		list.push({
			label: "Sick days this year",
			value: d.sick_types_configured ? formatNumber(d.sick_days) : "—",
			muted: !d.sick_types_configured,
		})
	}
	if (d.can_see_contracts) {
		const c = d.contract
		list.push({ label: "Contract", value: c ? `${formatPercent(c.fte_percentage)} · ${formatNumber(c.weekly_hours)} h/week` : "none in force", muted: !c })
		if (c) {
			list.push({ label: "Contract end", value: c.valid_until ? formatDate(c.valid_until) : "open-ended", muted: !c.valid_until })
			list.push({
				label: "Leave days per year",
				value: c.contract_type === "Employed" ? `${formatNumber(c.leave_days_per_year)} at ${formatNumber(c.working_days_per_week)} days/week` : "—",
				muted: c.contract_type !== "Employed",
			})
		}
	}
	return list
})

/** "05-17" → day and month in the site's date order, never a year (#1833, Decision 4). */
function formatBirthday(value) {
	const [month, day] = value.split("-")
	const format = getDateFormat().toLowerCase()
	const separator = format.match(/[^a-z]/)?.[0] || "."
	return format.indexOf("mm") < format.indexOf("dd")
		? `${month}${separator}${day}`
		: `${day}${separator}${month}${separator === "." ? "." : ""}`
}

function deskUrl(doctype, name) {
	return `/app/${doctype.toLowerCase().replace(/ /g, "-")}/${encodeURIComponent(name)}`
}
</script>
