<template>
	<div class="flex h-full min-h-0 flex-col bg-surface-white">
		<div class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 px-5 py-2 text-sm">
			<button
				v-for="t in tabs"
				:key="t.key"
				type="button"
				class="rounded px-2 py-1"
				:class="tab === t.key ? 'bg-surface-gray-3 font-medium text-ink-gray-9' : 'text-ink-gray-6 hover:text-ink-gray-9'"
				@click="setQuery({ tab: t.key, skill: undefined, run: undefined })"
			>
				{{ t.label }}
			</button>
			<span v-if="overview?.agent" class="ml-auto text-xs text-ink-gray-5">
				{{ overview.agent.name }} · works as {{ overview.agent.user }}{{ overview.agent.enabled ? "" : " · disabled" }}
			</span>
		</div>

		<!-- Skills -->
		<div v-if="tab === 'skills'" class="flex min-h-0 flex-1 flex-col lg:flex-row">
			<div class="min-h-0 overflow-y-auto border-b border-outline-gray-2 lg:w-96 lg:flex-none lg:border-b-0 lg:border-r">
				<p v-if="loadingOverview" class="p-5 text-sm text-ink-gray-5">Loading…</p>
				<p v-else-if="error" class="p-5 text-sm text-ink-red-4">{{ error }}</p>
				<template v-else>
					<p class="px-5 pt-4 text-xs text-ink-gray-5">
						The AI runs these steps, phase by phase, on every new receipt. Counts are from the last {{ overview.stats_days }} days.
					</p>
					<div v-for="phase in phasesWithSkills" :key="phase.name" class="px-3 pt-3">
						<h3 class="px-2 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">{{ phase.name }}</h3>
						<button
							v-for="s in phase.skills"
							:key="s.name"
							type="button"
							class="mt-1 flex w-full items-start gap-2 rounded-md px-2 py-2 text-left text-sm"
							:class="selectedSkill === s.name ? 'bg-surface-gray-3' : 'hover:bg-surface-gray-2'"
							@click="setQuery({ skill: s.name })"
						>
							<input
								type="checkbox"
								:checked="!!s.enabled"
								:disabled="!overview.can_write"
								class="mt-0.5"
								title="Enabled"
								@click.stop
								@change="toggle(s, $event.target.checked)"
							/>
							<span class="min-w-0 flex-1">
								<span class="block truncate font-medium" :class="s.enabled ? 'text-ink-gray-9' : 'text-ink-gray-5'">{{ s.skill_name }}</span>
								<span class="block truncate text-xs text-ink-gray-5">
									<template v-if="s.party">{{ s.party }} · </template>{{ statsText(s.stats) }}
								</span>
							</span>
						</button>
					</div>
				</template>
			</div>
			<div class="min-h-0 flex-1 overflow-y-auto">
				<AiSkillEditor v-if="selectedSkill" :key="selectedSkill" :name="selectedSkill" @saved="loadOverview" />
				<p v-else class="p-5 text-sm text-ink-gray-5">Pick a skill to see and change its settings.</p>
			</div>
		</div>

		<!-- Learning -->
		<div v-else-if="tab === 'learning'" class="min-h-0 flex-1 overflow-y-auto p-5 text-sm">
			<p v-if="!learning" class="text-ink-gray-5">Loading…</p>
			<div v-else class="mx-auto flex max-w-5xl flex-col gap-6">
				<p class="text-ink-gray-6">
					In the last {{ learning.days }} days people corrected values in {{ learning.corrected_runs }} of {{ learning.runs }} AI runs.
					<template v-if="Object.keys(learning.by_field).length">
						Most often:
						{{ Object.entries(learning.by_field).sort((a, b) => b[1] - a[1]).map(([f, n]) => `${fieldLabel(f)} (${n})`).join(", ") }}.
					</template>
				</p>

				<section>
					<h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">Suggested rules</h3>
					<p v-if="!learning.suggestions.length" class="text-ink-gray-5">
						No suggestions. When someone corrects the invoice number, a date or an amount the AI read, a rule for that supplier is suggested here.
					</p>
					<div v-for="s in learning.suggestions" :key="s.name" class="mb-2 rounded-md border border-outline-gray-2 p-3">
						<div class="flex flex-wrap items-center gap-2">
							<span class="font-medium text-ink-gray-9">{{ s.skill_name }}</span>
							<span class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-[11px] text-ink-gray-7">{{ s.occurrences || 1 }}×</span>
							<span class="ml-auto flex gap-2" v-if="learning.can_write">
								<button type="button" class="btn" @click="dismiss(s)">Dismiss</button>
								<button type="button" class="btn-primary" @click="accept(s)">Use this rule</button>
							</span>
						</div>
						<p v-for="(rule, i) in s.rules" :key="i" class="mt-1 text-ink-gray-8">
							<span class="text-ink-gray-5">{{ rule.case_description }}:</span> {{ rule.action }}
							<span class="block text-xs text-ink-gray-5">{{ rule.reason }}</span>
						</p>
					</div>
				</section>

				<section>
					<h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">Corrections</h3>
					<p v-if="!learning.corrections.length" class="text-ink-gray-5">No corrections yet.</p>
					<table v-else class="w-full text-sm">
						<thead>
							<tr class="text-left text-[11px] uppercase tracking-wide text-ink-gray-5">
								<th class="py-1 pr-2">Receipt</th>
								<th class="py-1 pr-2">Supplier</th>
								<th class="py-1 pr-2">Field</th>
								<th class="py-1 pr-2">AI read</th>
								<th class="py-1 pr-2">Corrected to</th>
								<th class="py-1">By</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(c, i) in learning.corrections" :key="i" class="border-t border-outline-gray-1">
								<td class="py-1 pr-2">
									<router-link :to="{ name: 'ReceiptDetail', params: { name: c.reference_name } }" class="text-ink-blue-3 underline">{{ c.reference_name }}</router-link>
								</td>
								<td class="truncate py-1 pr-2">{{ c.supplier || "–" }}</td>
								<td class="py-1 pr-2">{{ fieldLabel(c.field) }}</td>
								<td class="py-1 pr-2 text-ink-red-4">{{ c.ai_value ?? "–" }}</td>
								<td class="py-1 pr-2 text-ink-green-3">{{ c.human_value ?? "–" }}</td>
								<td class="py-1 text-ink-gray-6">{{ c.user_name }}</td>
							</tr>
						</tbody>
					</table>
				</section>
			</div>
		</div>

		<!-- Runs -->
		<div v-else class="flex min-h-0 flex-1 flex-col lg:flex-row">
			<div class="min-h-0 overflow-y-auto border-b border-outline-gray-2 lg:w-[34rem] lg:flex-none lg:border-b-0 lg:border-r">
				<div class="flex items-center gap-2 px-5 py-3">
					<select v-model="runStatus" class="input w-40" @change="loadRuns">
						<option value="">All runs</option>
						<option v-for="s in ['Completed', 'Failed', 'Running', 'Queued']" :key="s" :value="s">{{ s }}</option>
					</select>
					<button type="button" class="btn" @click="loadRuns">Refresh</button>
				</div>
				<p v-if="loadingRuns" class="px-5 text-sm text-ink-gray-5">Loading…</p>
				<p v-else-if="!runs.length" class="px-5 text-sm text-ink-gray-5">No runs yet.</p>
				<button
					v-for="r in runs"
					:key="r.name"
					type="button"
					class="block w-full border-t border-outline-gray-1 px-5 py-2 text-left text-sm"
					:class="selectedRun === r.name ? 'bg-surface-gray-3' : 'hover:bg-surface-gray-2'"
					@click="setQuery({ run: r.name })"
				>
					<span class="flex items-center gap-2">
						<span class="font-medium text-ink-gray-9">{{ r.reference_name }}</span>
						<span class="rounded px-1.5 py-0.5 text-[11px]" :class="r.status === 'Failed' ? 'bg-surface-red-1 text-ink-red-4' : 'bg-surface-gray-2 text-ink-gray-7'">{{ r.status }}</span>
						<span v-if="r.decision" class="text-xs text-ink-gray-6">{{ decisionLabel(r.decision) }}</span>
						<span class="ml-auto text-xs text-ink-gray-5">{{ when(r.creation) }}</span>
					</span>
					<span class="block truncate text-xs text-ink-gray-5">
						{{ r.trigger }} · {{ r.llm_calls || 0 }} Mistral calls · {{ r.duration ? `${Math.round(r.duration)} s` : "–" }}
						<template v-if="r.flag_count"> · {{ r.flag_count }} points to check</template>
						<template v-if="r.error"> · {{ r.error }}</template>
					</span>
				</button>
			</div>
			<div class="min-h-0 flex-1 overflow-y-auto p-5 text-sm">
				<p v-if="!selectedRun" class="text-ink-gray-5">Pick a run to see what each step did.</p>
				<p v-else-if="!run" class="text-ink-gray-5">Loading…</p>
				<template v-else>
					<div class="flex flex-wrap items-center gap-2">
						<h2 class="text-base font-medium">{{ run.name }}</h2>
						<router-link :to="{ name: 'ReceiptDetail', params: { name: run.reference_name } }" class="text-ink-blue-3 underline">{{ run.reference_name }}</router-link>
					</div>
					<p class="text-xs text-ink-gray-5">{{ run.status }} · {{ run.trigger }} · {{ run.mode }} · {{ run.llm_model || "no model" }} · {{ when(run.creation) }}</p>
					<p v-if="run.summary" class="mt-2">{{ run.summary }}</p>
					<p v-if="run.error" class="mt-2 text-ink-red-4">{{ run.error }}</p>
					<h3 class="mt-4 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">Steps</h3>
					<ol class="mt-1 space-y-2">
						<li v-for="(step, i) in run.steps" :key="i" class="rounded-md border border-outline-gray-2 p-2">
							<span class="flex items-center gap-2">
								<span class="font-medium">{{ step.skill_name || step.skill }}</span>
								<span class="text-xs text-ink-gray-5">{{ step.phase }}</span>
								<span class="ml-auto rounded px-1.5 py-0.5 text-[11px]" :class="stepClass(step.status)">{{ step.status }}</span>
								<span v-if="step.confidence != null" class="text-xs text-ink-gray-5">{{ Math.round(step.confidence) }} %</span>
							</span>
							<span v-if="step.message" class="block text-xs text-ink-gray-6">{{ step.message }}</span>
						</li>
					</ol>
					<template v-if="run.flags.length">
						<h3 class="mt-4 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">Points found</h3>
						<ul class="mt-1 space-y-0.5">
							<li v-for="(flag, i) in run.flags" :key="i" :class="flag.severity === 'block' ? 'text-ink-red-4' : flag.severity === 'warn' ? 'text-ink-amber-3' : 'text-ink-gray-6'">
								{{ flag.message }}
							</li>
						</ul>
					</template>
					<template v-if="run.classification.length">
						<h3 class="mt-4 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">Expense accounts</h3>
						<ul class="mt-1 space-y-1">
							<li v-for="line in run.classification" :key="line.row">
								<span class="font-medium">{{ line.description }}</span>
								<span :class="line.account ? 'text-ink-green-3' : 'text-ink-amber-3'"> → {{ line.account ? line.account.replace(/ - [^-]+$/, "") : "unclear" }}</span>
								<span class="block text-xs text-ink-gray-5">{{ line.reason }}</span>
							</li>
						</ul>
					</template>
				</template>
			</div>
		</div>
	</div>
</template>

<script setup>
// The AI Accountant: its skills (settings, rules, dry run) and what its runs did.
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call, toast } from "frappe-ui"
import AiSkillEditor from "../components/AiSkillEditor.vue"

const API = "phamos.api.ai_skills"
const route = useRoute()
const router = useRouter()

const tabs = [
	{ key: "skills", label: "Skills" },
	{ key: "runs", label: "Runs" },
	{ key: "learning", label: "Learning" },
]
const tab = computed(() => (["runs", "learning"].includes(route.query.tab) ? route.query.tab : "skills"))
const selectedSkill = computed(() => route.query.skill || "")
const selectedRun = computed(() => route.query.run || "")

function setQuery(patch) {
	router.replace({ query: { ...route.query, ...patch } })
}

// --- skills ---
const overview = ref(null)
const loadingOverview = ref(false)
const error = ref("")

async function loadOverview() {
	loadingOverview.value = !overview.value
	try {
		overview.value = await call(`${API}.get_ai_skills`, { doctype: "Accounting Receipt" })
		error.value = ""
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load the AI skills"
	} finally {
		loadingOverview.value = false
	}
}
loadOverview()

const phasesWithSkills = computed(() =>
	(overview.value?.phases || [])
		.map((name) => ({ name, skills: overview.value.skills.filter((s) => s.phase === name) }))
		.filter((p) => p.skills.length)
)

function statsText(stats) {
	if (!stats?.runs) return "no runs yet"
	const unsure = (stats.Uncertain || 0) + (stats.Failed || 0)
	const errors = stats.Error || 0
	return [`${stats.runs} runs`, unsure ? `${unsure} unsure` : "", errors ? `${errors} errors` : ""].filter(Boolean).join(" · ")
}

async function toggle(skill, enabled) {
	try {
		await call(`${API}.set_skill_enabled`, { name: skill.name, enabled: enabled ? 1 : 0 })
		skill.enabled = enabled ? 1 : 0
		toast({ title: `${skill.skill_name} ${enabled ? "enabled" : "disabled"}`, icon: "check-circle", iconClasses: "text-ink-green-3" })
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "Could not change the skill", icon: "x-circle", iconClasses: "text-ink-red-4" })
		await loadOverview()
	}
}

// --- runs ---
const runs = ref([])
const runStatus = ref("")
const loadingRuns = ref(false)
const run = ref(null)

async function loadRuns() {
	loadingRuns.value = true
	try {
		runs.value = await call(`${API}.get_agent_runs`, { doctype: "Accounting Receipt", status: runStatus.value || null, limit: 100 })
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "Could not load the runs", icon: "x-circle", iconClasses: "text-ink-red-4" })
	} finally {
		loadingRuns.value = false
	}
}

watch(tab, (value) => value === "runs" && !runs.value.length && loadRuns(), { immediate: true })
watch(
	selectedRun,
	async (name) => {
		run.value = null
		if (!name) return
		try {
			run.value = await call(`${API}.get_agent_run`, { name })
		} catch (e) {
			toast({ title: e?.messages?.[0] || e?.message || "Could not load the run", icon: "x-circle", iconClasses: "text-ink-red-4" })
		}
	},
	{ immediate: true }
)

// --- learning ---
const learning = ref(null)

async function loadLearning() {
	try {
		learning.value = await call(`${API}.get_learning`, { doctype: "Accounting Receipt" })
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "Could not load what the AI learned", icon: "x-circle", iconClasses: "text-ink-red-4" })
	}
}
watch(tab, (value) => value === "learning" && loadLearning(), { immediate: true })

async function accept(suggestion) {
	try {
		await call(`${API}.accept_suggestion`, { name: suggestion.name })
		toast({ title: `Rule on: ${suggestion.skill_name}`, icon: "check-circle", iconClasses: "text-ink-green-3" })
		await Promise.all([loadLearning(), loadOverview()])
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "Could not use the rule", icon: "x-circle", iconClasses: "text-ink-red-4" })
	}
}

async function dismiss(suggestion) {
	try {
		await call(`${API}.dismiss_suggestion`, { name: suggestion.name })
		await loadLearning()
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "Could not dismiss the suggestion", icon: "x-circle", iconClasses: "text-ink-red-4" })
	}
}

const FIELD_LABELS = {
	supplier_reference: "Invoice number",
	posting_date: "Invoice date",
	due_date: "Due date",
	sum: "Total",
	net_total: "Net",
	total_taxes: "Tax",
	supplier: "Supplier",
	currency: "Currency",
	receipt_type: "Receipt type",
	supplier_tax_id: "VAT ID",
	supplier_iban: "IBAN",
	payment_reference: "Payment reference",
}

function fieldLabel(field) {
	return FIELD_LABELS[field] || field
}

function decisionLabel(decision) {
	return { auto_datev: "→ DATEV", approve_to_pay: "→ approve", needs_human: "→ person", not_a_voucher: "→ not a voucher" }[decision] || decision
}

function stepClass(status) {
	if (status === "Passed") return "bg-surface-green-2 text-ink-green-3"
	if (status === "Error" || status === "Failed") return "bg-surface-red-1 text-ink-red-4"
	if (status === "Uncertain") return "bg-surface-amber-1 text-ink-amber-3"
	return "bg-surface-gray-2 text-ink-gray-6"
}

function when(value) {
	if (!value) return ""
	const date = new Date(value.replace(" ", "T"))
	return date.toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })
}
</script>
