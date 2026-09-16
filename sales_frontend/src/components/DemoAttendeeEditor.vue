<template>
	<div>
		<div class="mb-2 flex items-center justify-between gap-2">
			<span class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Attendees</span>
			<span v-if="modelValue.length" class="text-xs text-ink-gray-6">
				{{ attendedCount }} of {{ modelValue.length }} attended
			</span>
		</div>

		<div class="rounded-md border border-outline-gray-2 bg-surface-white">
			<div
				v-if="!modelValue.length"
				class="px-3 py-4 text-center text-sm text-ink-gray-5"
			>
				Nobody added yet.
			</div>

			<!-- Read-style rows that become editable on focus, as the lead's next
			     steps do — a list of people should be scannable first. -->
			<div
				v-for="(row, index) in modelValue"
				:key="index"
				class="group flex items-center gap-2 border-b border-outline-gray-1 px-2 py-1.5 last:border-0 focus-within:bg-surface-gray-1"
			>
				<div class="min-w-0 flex-1">
					<input
						:value="row.full_name"
						type="text"
						placeholder="Name"
						class="h-6 w-full truncate border-none bg-transparent px-1 text-sm font-medium text-ink-gray-8 focus:ring-0"
						@change="update(index, 'full_name', $event.target.value)"
					/>
					<input
						:value="row.email"
						type="text"
						placeholder="email@example.com"
						class="h-5 w-full truncate border-none bg-transparent px-1 text-xs text-ink-gray-6 focus:ring-0"
						@change="update(index, 'email', $event.target.value)"
					/>
				</div>

				<select
					:value="row.participation || 'Required'"
					class="h-6 flex-none rounded border-none bg-transparent px-1 text-xs text-ink-gray-7 focus:ring-0"
					aria-label="Participation"
					@change="update(index, 'participation', $event.target.value)"
				>
					<option value="Required">Required</option>
					<option value="Optional">Optional</option>
				</select>

				<select
					:value="row.audience || 'External'"
					class="h-6 flex-none rounded border-none bg-transparent px-1 text-xs text-ink-gray-7 focus:ring-0"
					aria-label="Audience"
					@change="update(index, 'audience', $event.target.value)"
				>
					<option value="Internal">Internal</option>
					<option value="External">External</option>
				</select>

				<!-- Recorded after the demo; blank means nobody has said yet. -->
				<select
					:value="row.attended || ''"
					class="h-6 w-24 flex-none rounded border border-outline-gray-2 bg-surface-white px-1 text-xs"
					:class="attendedClass(row.attended)"
					aria-label="Attended"
					@change="update(index, 'attended', $event.target.value)"
				>
					<option value="">Attended?</option>
					<option value="Yes">Attended</option>
					<option value="No">No-show</option>
				</select>

				<button
					type="button"
					class="flex-none rounded p-0.5 text-ink-gray-5 opacity-0 hover:bg-surface-gray-2 hover:text-ink-gray-9 focus-visible:opacity-100 group-focus-within:opacity-100 group-hover:opacity-100"
					title="Remove"
					@click="remove(index)"
				>
					<FeatherIcon name="x" class="h-3.5 w-3.5" />
				</button>
			</div>
		</div>

		<div class="mt-1.5 flex flex-wrap items-center gap-1.5">
			<button
				type="button"
				class="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				@click="add()"
			>
				<FeatherIcon name="plus" class="h-3.5 w-3.5" />
				<span>Add attendee</span>
			</button>

			<!-- The lead's own contacts are who a demo is usually held with. -->
			<button
				v-for="suggestion in availableSuggestions"
				:key="suggestion.email || suggestion.full_name"
				type="button"
				class="rounded-full border border-dashed border-outline-gray-3 px-2 py-0.5 text-xs text-ink-gray-8 hover:border-outline-gray-4 hover:bg-surface-gray-2"
				:title="suggestion.email"
				@click="add(suggestion)"
			>
				+ {{ suggestion.full_name }}
			</button>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { call } from "frappe-ui"

const props = defineProps({
	/** [{ full_name, email, participation, audience, attended, user, contact }] */
	modelValue: { type: Array, default: () => [] },
	lead: { type: String, default: "" },
})

const emit = defineEmits(["update:modelValue"])

const suggestions = ref([])

const attendedCount = computed(() => props.modelValue.filter((r) => r.attended === "Yes").length)

/** Don't offer someone who's already on the list. */
const availableSuggestions = computed(() => {
	const used = new Set(
		props.modelValue.map((r) => (r.email || "").toLowerCase()).filter(Boolean)
	)
	return suggestions.value.filter((s) => s.email && !used.has(s.email.toLowerCase()))
})

function attendedClass(value) {
	if (value === "Yes") return "border-outline-green-2 text-ink-green-3"
	if (value === "No") return "border-outline-red-2 text-ink-red-4"
	return "text-ink-gray-5"
}

function update(index, field, value) {
	const rows = props.modelValue.map((row, i) =>
		i === index ? { ...row, [field]: value || null } : row
	)
	emit("update:modelValue", rows)
}

function add(suggestion) {
	emit("update:modelValue", [
		...props.modelValue,
		{
			full_name: suggestion?.full_name || "",
			email: suggestion?.email || "",
			contact: suggestion?.contact || null,
			user: null,
			participation: "Required",
			audience: "External",
			attended: null,
		},
	])
}

function remove(index) {
	emit(
		"update:modelValue",
		props.modelValue.filter((_, i) => i !== index)
	)
}

async function loadSuggestions() {
	if (!props.lead) return
	try {
		const data = await call("phamos.api.sales_leads.get_lead_contacts", { lead: props.lead })
		suggestions.value = (data.contacts || []).map((contact) => ({
			full_name: contact.full_name,
			email: contact.email_id,
			contact: contact.name,
		}))
	} catch (e) {
		suggestions.value = []
	}
}

watch(() => props.lead, loadSuggestions)
onMounted(loadSuggestions)
</script>
