<template>
	<div v-if="!skill" class="p-5 text-sm text-ink-gray-5">Loading…</div>
	<div v-else class="flex flex-col gap-5 p-5 text-sm" @keydown.meta.s.prevent="save" @keydown.ctrl.s.prevent="save">
		<div class="flex flex-wrap items-center gap-3">
			<input v-model="draft.skill_name" :disabled="!canWrite" class="input min-w-0 flex-1 text-base font-medium" />
			<label class="flex items-center gap-2 text-ink-gray-7">
				<input v-model="draft.enabled" type="checkbox" :disabled="!canWrite" />
				Enabled
			</label>
			<button type="button" class="btn-primary" :disabled="!canWrite || !dirty || saving" @click="save">
				{{ saving ? "Saving…" : dirty ? "Save" : "Saved" }}
			</button>
		</div>
		<p class="-mt-3 text-xs text-ink-gray-5">
			{{ skill.phase }} · step {{ skill.handler || "prompt rules only" }}
			<template v-if="skill.party"> · only for {{ skill.party_doctype }} {{ skill.party }}</template>
			· {{ skill.name }}
		</p>

		<label class="field">
			<span>What it does</span>
			<textarea v-model="draft.description" :disabled="!canWrite" rows="2" class="input"></textarea>
		</label>

		<section v-if="skill.param_fields.length">
			<h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">Settings</h3>
			<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
				<label v-for="field in skill.param_fields" :key="field.key" :class="field.type === 'check' ? 'flex items-start gap-2 sm:col-span-2' : 'field'">
					<template v-if="field.type === 'check'">
						<input v-model="draft.params[field.key]" type="checkbox" :true-value="1" :false-value="0" :disabled="!canWrite" class="mt-0.5" />
						<span>
							{{ field.label }}
							<span v-if="field.help" class="block text-xs text-ink-gray-5">{{ field.help }}</span>
						</span>
					</template>
					<template v-else>
						<span>{{ field.label }}</span>
						<input v-model.number="draft.params[field.key]" type="number" :min="field.min" :max="field.max" :disabled="!canWrite" class="input" />
						<span v-if="field.help" class="text-xs text-ink-gray-5">{{ field.help }}</span>
					</template>
				</label>
			</div>
		</section>

		<section v-if="skill.phase === 'Extract' || draft.prompt_rules.length">
			<div class="mb-2 flex items-center justify-between">
				<h3 class="text-xs font-semibold uppercase tracking-wide text-ink-gray-5">Rules for Mistral</h3>
				<button v-if="canWrite" type="button" class="text-xs text-ink-gray-6 hover:text-ink-gray-9" @click="addRule">+ Add rule</button>
			</div>
			<p v-if="!draft.prompt_rules.length" class="text-ink-gray-5">No rules. Add one when the AI keeps reading a field wrong.</p>
			<div v-for="(rule, i) in draft.prompt_rules" :key="rule.name || `new-${i}`" class="mb-2 grid grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)_auto] items-start gap-2 rounded-md border border-outline-gray-2 p-2">
				<input v-model="rule.enabled" type="checkbox" :true-value="1" :false-value="0" :disabled="!canWrite" class="mt-2" title="Enabled" />
				<textarea v-model="rule.case_description" :disabled="!canWrite" rows="2" class="input" placeholder="When… (e.g. an Apple invoice shows Document and Order numbers)"></textarea>
				<textarea v-model="rule.action" :disabled="!canWrite" rows="2" class="input" placeholder="Then… (e.g. the invoice number is the one after Document)"></textarea>
				<button v-if="canWrite" type="button" class="mt-1 text-ink-gray-5 hover:text-ink-red-4" title="Remove" @click="draft.prompt_rules.splice(i, 1)">✕</button>
			</div>
		</section>

		<section class="grid grid-cols-1 gap-3 sm:grid-cols-3">
			<label class="field">
				<span>Order in phase</span>
				<input v-model.number="draft.order" type="number" :disabled="!canWrite" class="input" />
			</label>
			<label class="field">
				<span>When it fails</span>
				<select v-model="draft.on_fail" :disabled="!canWrite" class="input">
					<option v-for="option in skill.on_fail_options" :key="option" :value="option">{{ option }}</option>
				</select>
			</label>
			<label class="field">
				<span>Unsure below (%)</span>
				<input v-model.number="draft.min_confidence" type="number" min="0" max="100" :disabled="!canWrite" class="input" />
			</label>
		</section>
		<p v-if="skill.condition" class="text-xs text-ink-gray-5">Runs only when: <code>{{ skill.condition }}</code> (edit in Desk)</p>

		<section v-if="skill.has_dry_run" class="rounded-md border border-outline-gray-2 bg-surface-gray-1 p-3">
			<h3 class="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">Dry run</h3>
			<div class="flex flex-wrap items-center gap-2">
				<div class="min-w-56 flex-1">
					<FrappeLink v-model="dryRunReceipt" doctype="Accounting Receipt" placeholder="Receipt to try it on" />
				</div>
				<button type="button" class="btn" :disabled="!dryRunReceipt || running" @click="dryRun">{{ running ? "Running…" : "Try with these settings" }}</button>
			</div>
			<p class="mt-1 text-xs text-ink-gray-5">Uses the settings above, saved or not. Nothing is changed, and Mistral is not called.</p>
			<div v-if="result" class="mt-3">
				<pre v-if="result.kind === 'prompt'" class="max-h-96 overflow-auto whitespace-pre-wrap rounded bg-surface-white p-2 text-xs text-ink-gray-8">{{ result.prompt }}</pre>
				<div v-else-if="result.kind === 'decide'">
					<p class="font-medium" :class="result.decision === 'needs_human' || result.decision === 'not_a_voucher' ? 'text-ink-amber-3' : 'text-ink-green-3'">
						{{ result.summary }} · {{ result.confidence }} %
					</p>
					<p class="text-xs text-ink-gray-5">{{ result.history_count }} earlier receipts or invoices of this supplier</p>
					<ul class="mt-1 space-y-0.5">
						<li v-for="(flag, i) in result.flags" :key="i" :class="flagClass(flag)">{{ flag.message }}</li>
					</ul>
				</div>
				<div v-else-if="result.kind === 'classify'">
					<p class="font-medium">{{ result.assigned }} of {{ result.open }} open lines assigned, {{ result.unclear }} unclear</p>
					<p class="text-xs text-ink-gray-5">{{ result.note }}</p>
					<ul class="mt-1 space-y-1">
						<li v-for="line in result.lines" :key="line.row">
							<span class="font-medium">{{ line.description }}</span>
							<span :class="line.account ? 'text-ink-green-3' : 'text-ink-amber-3'"> → {{ line.account ? accountLabel(line.account) : "unclear" }}</span>
							<span v-if="line.score" class="text-ink-gray-5"> · {{ Math.round(line.score) }} %</span>
							<span class="block text-xs text-ink-gray-5">{{ line.reason }}</span>
						</li>
						<li v-if="!result.lines.length" class="text-ink-gray-5">Every line already has an account.</li>
					</ul>
				</div>
				<p v-else class="text-ink-gray-5">{{ result.note }}</p>
			</div>
		</section>
	</div>
</template>

<script setup>
// Edit one AI skill: settings as form fields, prompt rules, and a dry run on a receipt.
import { computed, reactive, ref, watch } from "vue"
import { call, toast } from "frappe-ui"
import FrappeLink from "@spa/components/FrappeLink.vue"

const API = "phamos.api.ai_skills"

const props = defineProps({ name: { type: String, required: true } })
const emit = defineEmits(["saved"])

const skill = ref(null)
const draft = reactive({ skill_name: "", enabled: 0, description: "", params: {}, prompt_rules: [], order: 0, on_fail: "", min_confidence: 0 })
const saved = ref("")
const saving = ref(false)
const dryRunReceipt = ref("")
const running = ref(false)
const result = ref(null)

const canWrite = computed(() => !!skill.value?.can_write)
const dirty = computed(() => JSON.stringify(snapshot()) !== saved.value)

function snapshot() {
	return {
		skill_name: draft.skill_name,
		enabled: draft.enabled ? 1 : 0,
		description: draft.description || "",
		params: draft.params,
		prompt_rules: draft.prompt_rules,
		order: draft.order,
		on_fail: draft.on_fail,
		min_confidence: draft.min_confidence,
	}
}

function fill(data) {
	skill.value = data
	Object.assign(draft, {
		skill_name: data.skill_name,
		enabled: data.enabled ? 1 : 0,
		description: data.description || "",
		params: { ...data.params },
		prompt_rules: data.prompt_rules.map((r) => ({ ...r })),
		order: data.order,
		on_fail: data.on_fail,
		min_confidence: data.min_confidence || 0,
	})
	saved.value = JSON.stringify(snapshot())
}

async function load() {
	skill.value = null
	result.value = null
	try {
		fill(await call(`${API}.get_ai_skill`, { name: props.name }))
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "Could not load the skill", icon: "x-circle", iconClasses: "text-ink-red-4" })
	}
}
watch(() => props.name, load, { immediate: true })

function addRule() {
	draft.prompt_rules.push({ enabled: 1, case_description: "", action: "", reason: "" })
}

async function save() {
	if (!canWrite.value || !dirty.value || saving.value) return
	saving.value = true
	try {
		fill(await call(`${API}.save_ai_skill`, { name: props.name, values: snapshot(), modified: skill.value.modified }))
		toast({ title: "Skill saved", icon: "check-circle", iconClasses: "text-ink-green-3" })
		emit("saved", skill.value)
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "Could not save the skill", icon: "x-circle", iconClasses: "text-ink-red-4" })
	} finally {
		saving.value = false
	}
}

async function dryRun() {
	running.value = true
	result.value = null
	try {
		result.value = await call(`${API}.dry_run_ai_skill`, {
			skill: props.name,
			reference_name: dryRunReceipt.value,
			params: draft.params,
			prompt_rules: draft.prompt_rules,
		})
	} catch (e) {
		toast({ title: e?.messages?.[0] || e?.message || "The dry run failed", icon: "x-circle", iconClasses: "text-ink-red-4" })
	} finally {
		running.value = false
	}
}

function accountLabel(account) {
	return (account || "").replace(/ - [^-]+$/, "")
}

function flagClass(flag) {
	return flag.severity === "block" ? "text-ink-red-4" : flag.severity === "warn" ? "text-ink-amber-3" : "text-ink-gray-6"
}

defineExpose({ dirty })
</script>
