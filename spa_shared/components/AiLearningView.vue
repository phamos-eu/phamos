<template>
	<div ref="root" class="flex flex-col gap-6 text-sm outline-none" tabindex="0" @keydown="onKey">
		<p v-if="error" class="text-ink-red-4">{{ error }}</p>
		<p v-else-if="!learning" class="text-ink-gray-5">{{ __("Loading…") }}</p>
		<template v-else>
			<p class="text-ink-gray-6">
				{{ __("In the last {0} days people corrected {1} of {2} AI runs.", [learning.days, learning.corrected_runs, learning.runs]) }}
				<template v-if="topFields.length">
					{{ __("Most often:") }} {{ topFields.join(", ") }}.
				</template>
			</p>

			<!-- Suggested rules -->
			<section>
				<h3 class="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">{{ __("Suggested rules") }}</h3>
				<p v-if="learning.can_write && learning.suggestions.length" class="mb-2 text-xs text-ink-gray-5">
					{{ __("↑ ↓ pick a rule · Enter uses it · Del dismisses it") }}
				</p>
				<p v-if="!learning.suggestions.length" class="text-ink-gray-5">{{ emptyText || __("No suggestions yet.") }}</p>
				<div
					v-for="(s, i) in learning.suggestions"
					:key="s.name"
					class="mb-2 rounded-md border p-3"
					:class="i === selected ? 'border-outline-gray-4 bg-surface-gray-1' : 'border-outline-gray-2'"
					@click="selected = i"
				>
					<div class="flex flex-wrap items-center gap-2">
						<span class="font-medium text-ink-gray-9">{{ s.skill_name }}</span>
						<span class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-[11px] text-ink-gray-7">{{ s.occurrences || 1 }}×</span>
						<span v-if="s.party" class="text-xs text-ink-gray-5">{{ s.party }}</span>
						<span v-if="learning.can_write" class="ml-auto flex gap-2">
							<button type="button" class="btn" :disabled="busy" @click.stop="dismiss(s)">{{ __("Dismiss") }}</button>
							<button type="button" class="btn-primary" :disabled="busy" @click.stop="accept(s)">{{ __("Use this rule") }}</button>
						</span>
					</div>
					<p v-if="s.description" class="mt-1 text-xs text-ink-gray-5">{{ s.description }}</p>
					<p v-if="s.mapping" class="mt-1 text-ink-gray-8">
						<span class="text-ink-gray-5">{{ __("E-mails from {0}", [s.mapping.match]) }}:</span>
						{{ Object.entries(s.mapping.values || {}).map(([f, v]) => `${fieldLabel(f)} → ${v}`).join(", ") }}
					</p>
					<div v-for="rule in edits[s.name] || []" :key="rule.name" class="mt-2 flex flex-col gap-1">
						<template v-if="learning.can_write">
							<label class="text-xs text-ink-gray-5">{{ __("When") }}</label>
							<textarea v-model="rule.case_description" rows="1" class="input w-full" @keydown.stop />
							<label class="text-xs text-ink-gray-5">{{ __("Then") }}</label>
							<textarea v-model="rule.action" rows="2" class="input w-full" @keydown.stop />
						</template>
						<p v-else class="text-ink-gray-8">
							<span class="text-ink-gray-5">{{ rule.case_description }}:</span> {{ rule.action }}
						</p>
						<span class="text-xs text-ink-gray-5">{{ rule.reason }}</span>
						<span v-if="s.party_doctype === 'Customer'" class="text-xs text-ink-amber-3">
							{{ __("May quote the customer's Issue: check the wording before using it.") }}
						</span>
					</div>
				</div>
			</section>

			<!-- Rates -->
			<section v-if="rateRows.length">
				<h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">{{ __("Corrected how often") }}</h3>
				<table class="w-full max-w-xl text-sm">
					<thead>
						<tr class="text-left text-[11px] uppercase tracking-wide text-ink-gray-5">
							<th class="py-1 pr-2">{{ __("Step or field") }}</th>
							<th class="py-1 pr-2 text-right">{{ __("Set by the AI") }}</th>
							<th class="py-1 pr-2 text-right">{{ __("Corrected") }}</th>
							<th class="py-1 text-right">%</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="row in rateRows" :key="row.key" class="border-t border-outline-gray-1" :class="row.group ? 'font-medium' : 'text-ink-gray-6'">
							<td class="py-1 pr-2" :class="row.group ? '' : 'pl-4'">{{ row.label }}</td>
							<td class="py-1 pr-2 text-right">{{ row.set }}</td>
							<td class="py-1 pr-2 text-right">{{ row.corrected }}</td>
							<td class="py-1 text-right">{{ row.set ? Math.round((100 * row.corrected) / row.set) : 0 }}</td>
						</tr>
					</tbody>
				</table>
			</section>

			<!-- Recent runs -->
			<section>
				<h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">{{ __("Recent runs") }}</h3>
				<p v-if="!learning.recent_runs.length" class="text-ink-gray-5">{{ __("No runs yet.") }}</p>
				<table v-else class="w-full text-sm">
					<tbody>
						<tr v-for="r in learning.recent_runs" :key="r.name" class="border-t border-outline-gray-1">
							<td class="py-1 pr-2"><RefLink :name="r.reference_name" /></td>
							<td class="py-1 pr-2">
								<span class="rounded px-1.5 py-0.5 text-[11px]" :class="outcomeClass(r.outcome)">{{ outcomeLabel(r.outcome) }}</span>
							</td>
							<td class="py-1 pr-2 text-ink-gray-6">{{ r.corrected_by_name || "" }}</td>
							<td class="py-1 text-right text-xs text-ink-gray-5">{{ when(r.creation) }}</td>
						</tr>
					</tbody>
				</table>
			</section>

			<!-- Corrections -->
			<section>
				<h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">{{ __("Corrections") }}</h3>
				<p v-if="!learning.corrections.length" class="text-ink-gray-5">{{ __("No corrections yet.") }}</p>
				<table v-else class="w-full text-sm">
					<thead>
						<tr class="text-left text-[11px] uppercase tracking-wide text-ink-gray-5">
							<th class="py-1 pr-2">{{ referenceLabel }}</th>
							<th class="py-1 pr-2">{{ partyLabel }}</th>
							<th class="py-1 pr-2">{{ __("Field") }}</th>
							<th class="py-1 pr-2">{{ __("AI set") }}</th>
							<th class="py-1 pr-2">{{ __("Corrected to") }}</th>
							<th class="py-1">{{ __("By") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="(c, i) in learning.corrections" :key="i" class="border-t border-outline-gray-1">
							<td class="py-1 pr-2"><RefLink :name="c.reference_name" /></td>
							<td class="truncate py-1 pr-2">{{ c.party || "–" }}</td>
							<td class="py-1 pr-2">{{ fieldLabel(c.field) }}</td>
							<td class="py-1 pr-2 text-ink-red-4">{{ c.ai_value ?? "–" }}</td>
							<td class="py-1 pr-2 text-ink-green-3">{{ c.human_value ?? "–" }}</td>
							<td class="py-1 text-ink-gray-6">{{ c.user_name }}</td>
						</tr>
					</tbody>
				</table>
			</section>
		</template>
	</div>
</template>

<script setup>
// One "AI learning" view for any agent (#2226): suggested rules to use or dismiss (wording editable),
// how often people corrected what the AI set, recent runs with their outcome, and the corrections.
// Used by the Accounting Cockpit (AI Accountant) and the General Management Cockpit (Issue Assistant).
import { computed, defineComponent, h, ref, resolveComponent } from "vue"
import { call, toast } from "frappe-ui"
import { __ } from "@spa/utils/i18n.js"

const props = defineProps({
	doctype: { type: String, required: true },
	fieldLabels: { type: Object, default: () => ({}) },
	groupLabels: { type: Object, default: () => ({}) },
	partyLabel: { type: String, default: "" },
	referenceLabel: { type: String, default: "" },
	// name → a router location (object) or a URL (string, opened in Desk)
	referenceTo: { type: Function, default: null },
	emptyText: { type: String, default: "" },
})
const emit = defineEmits(["changed"])

const API = "phamos.api.ai_skills"
const root = ref(null)
const learning = ref(null)
const error = ref("")
const edits = ref({})
const selected = ref(0)
const busy = ref(false)

const partyLabel = computed(() => props.partyLabel || __("Party"))
const referenceLabel = computed(() => props.referenceLabel || __("Record"))

const RefLink = defineComponent({
	props: { name: String },
	setup(p) {
		return () => {
			if (!p.name) return "–"
			const to = props.referenceTo ? props.referenceTo(p.name) : null
			if (!to) return p.name
			if (typeof to === "string") return h("a", { href: to, target: "_blank", class: "text-ink-blue-3 underline" }, p.name)
			return h(resolveComponent("router-link"), { to, class: "text-ink-blue-3 underline" }, () => p.name)
		}
	},
})

async function load() {
	try {
		learning.value = await call(`${API}.get_learning`, { doctype: props.doctype })
		edits.value = Object.fromEntries(learning.value.suggestions.map((s) => [s.name, s.rules.map((r) => ({ ...r }))]))
		selected.value = Math.min(selected.value, Math.max(learning.value.suggestions.length - 1, 0))
		error.value = ""
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not load what the AI learned")
	}
}
load()
defineExpose({ load })

const topFields = computed(() =>
	Object.entries(learning.value?.by_field || {})
		.sort((a, b) => b[1] - a[1])
		.map(([f, n]) => `${fieldLabel(f)} (${n})`)
)

const rateRows = computed(() => {
	const rates = learning.value?.rates
	if (!rates) return []
	const rows = []
	for (const [group, total] of Object.entries(rates.groups || {})) {
		const fields = Object.entries(rates.fields || {}).filter(([f]) => (rates.field_groups || {})[f] === group)
		rows.push({ key: `g:${group}`, group: true, label: props.groupLabels[group] || fieldLabel(group), ...total })
		// a step of one field named like it needs no second line
		if (!(fields.length === 1 && fields[0][0] === group)) {
			for (const [field, entry] of fields) rows.push({ key: `f:${field}`, label: fieldLabel(field), ...entry })
		}
	}
	return rows
})

function fieldLabel(field) {
	return props.fieldLabels[field] || field
}

function changedRules(s) {
	const now = edits.value[s.name] || []
	return now.some((r, i) => r.case_description !== s.rules[i]?.case_description || r.action !== s.rules[i]?.action)
}

async function accept(s) {
	if (busy.value) return
	busy.value = true
	try {
		const args = { name: s.name }
		if (changedRules(s)) {
			args.prompt_rules = JSON.stringify(edits.value[s.name])
			args.modified = s.modified
		}
		await call(`${API}.accept_suggestion`, args)
		toast({ title: __("Rule on: {0}", [s.skill_name]), icon: "check-circle", iconClasses: "text-ink-green-3" })
		await load()
		emit("changed")
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || __("Could not use the rule"), icon: "x-circle", iconClasses: "text-ink-red-4" })
	} finally {
		busy.value = false
	}
}

async function dismiss(s, ask = false) {
	if (busy.value) return
	if (ask && !window.confirm(__("Dismiss the suggestion \"{0}\"? It won't be suggested again.", [s.skill_name]))) return
	busy.value = true
	try {
		await call(`${API}.dismiss_suggestion`, { name: s.name })
		await load()
		emit("changed")
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || __("Could not dismiss the suggestion"), icon: "x-circle", iconClasses: "text-ink-red-4" })
	} finally {
		busy.value = false
	}
}

function onKey(event) {
	const list = learning.value?.suggestions || []
	if (!list.length || ["TEXTAREA", "INPUT", "SELECT"].includes(event.target?.tagName)) return
	if (event.key === "ArrowDown") selected.value = Math.min(selected.value + 1, list.length - 1)
	else if (event.key === "ArrowUp") selected.value = Math.max(selected.value - 1, 0)
	else if (event.key === "Enter" && learning.value.can_write) accept(list[selected.value])
	else if ((event.key === "Delete" || event.key === "Backspace") && learning.value.can_write) dismiss(list[selected.value], true)
	else return
	event.preventDefault()
}

function outcomeLabel(outcome) {
	return outcome === "Corrected" ? __("Corrected") : outcome === "Accepted" ? __("Accepted") : __("Open")
}

function outcomeClass(outcome) {
	if (outcome === "Corrected") return "bg-surface-amber-1 text-ink-amber-3"
	if (outcome === "Accepted") return "bg-surface-green-2 text-ink-green-3"
	return "bg-surface-gray-2 text-ink-gray-6"
}

function when(value) {
	if (!value) return ""
	return new Date(value.replace(" ", "T")).toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })
}
</script>
