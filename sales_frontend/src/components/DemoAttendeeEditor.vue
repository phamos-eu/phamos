<template>
	<div>
		<div class="mb-2 flex items-center justify-between gap-2">
			<span class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Attendees</span>
			<span v-if="rows.length" class="text-xs text-ink-gray-6">{{ rows.length }}</span>
		</div>

		<div v-if="!rows.length" class="rounded-md border border-outline-gray-2 bg-surface-white p-4 text-center text-sm text-ink-gray-5">
			Nobody added yet. The lead is always invited; add whoever else is joining.
		</div>

		<div v-else class="space-y-1 rounded-md border border-outline-gray-2 bg-surface-white p-2">
			<!-- Read-style until focused, like the lead's next steps: a list of
			     people should scan as a list, not as a wall of inputs. -->
			<div
				v-for="(row, index) in rows"
				:key="index"
				class="group grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_auto_auto_auto] items-center gap-2 rounded border border-transparent px-1 py-0.5 focus-within:border-outline-gray-2 focus-within:bg-surface-gray-1 hover:border-outline-gray-2"
			>
				<input
					v-model="row.full_name"
					type="text"
					placeholder="Name"
					:title="row.full_name"
					class="h-6 min-w-0 truncate border-none bg-transparent px-1 text-sm text-ink-gray-8 focus:ring-0"
					@change="commit"
				/>
				<input
					v-model="row.email"
					type="text"
					placeholder="name@example.com"
					:title="row.email"
					class="h-6 min-w-0 truncate border-none bg-transparent px-1 text-xs text-ink-gray-7 focus:ring-0"
					@change="commit"
				/>
				<select
					v-model="row.participation"
					class="h-6 rounded border-none bg-transparent px-1 text-xs text-ink-gray-7 focus:ring-0"
					aria-label="Participation"
					@change="commit"
				>
					<option value="Required">Required</option>
					<option value="Optional">Optional</option>
				</select>
				<select
					v-model="row.audience"
					class="h-6 rounded border-none bg-transparent px-1 text-xs text-ink-gray-7 focus:ring-0"
					aria-label="Internal or external"
					@change="commit"
				>
					<option value="Internal">Internal</option>
					<option value="External">External</option>
				</select>
				<button
					type="button"
					class="rounded p-0.5 text-ink-gray-5 opacity-0 hover:bg-surface-gray-2 hover:text-ink-gray-9 focus-visible:opacity-100 group-focus-within:opacity-100 group-hover:opacity-100"
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
				@click="addBlank"
			>
				<FeatherIcon name="plus" class="h-3.5 w-3.5" />
				<span>Add attendee</span>
			</button>

			<!-- The people already on the lead, so the common case is a click. -->
			<button
				v-for="contact in availableContacts"
				:key="contact.name"
				type="button"
				class="rounded-full border border-dashed border-outline-gray-3 px-2 py-0.5 text-xs text-ink-gray-8 hover:border-outline-gray-4 hover:bg-surface-gray-2"
				:title="contact.email_id || contact.full_name"
				@click="addContact(contact)"
			>
				+ {{ contact.full_name }}
			</button>
		</div>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call } from "frappe-ui"

const props = defineProps({
	/** [{ contact, user, full_name, email, participation, audience }] */
	modelValue: { type: Array, default: () => [] },
	/** Lead the demo belongs to, for the contact suggestions. */
	lead: { type: String, default: "" },
})

const emit = defineEmits(["update:modelValue"])

const rows = ref([])
const contacts = ref([])

/** Local working copy: rows are edited in place, then emitted as a whole. */
watch(
	() => props.modelValue,
	(value) => {
		rows.value = (value || []).map((row) => ({ ...row }))
	},
	{ immediate: true, deep: false }
)

const availableContacts = computed(() => {
	const used = new Set(
		rows.value.map((row) => (row.email || "").trim().toLowerCase()).filter(Boolean)
	)
	return contacts.value.filter((c) => c.email_id && !used.has(c.email_id.toLowerCase()))
})

function commit() {
	// Blank rows are the user still typing, not something to save.
	emit(
		"update:modelValue",
		rows.value.filter((row) => (row.full_name || "").trim() || (row.email || "").trim())
	)
}

function addBlank() {
	rows.value.push({ full_name: "", email: "", participation: "Required", audience: "External" })
}

function addContact(contact) {
	rows.value.push({
		contact: contact.name,
		full_name: contact.full_name,
		email: contact.email_id,
		participation: "Required",
		audience: "External",
	})
	commit()
}

function remove(index) {
	rows.value.splice(index, 1)
	commit()
}

async function loadContacts() {
	if (!props.lead) return
	try {
		const data = await call("phamos.api.sales_leads.get_lead_contacts", { lead: props.lead })
		contacts.value = data.contacts || []
	} catch (e) {
		contacts.value = []
	}
}

watch(() => props.lead, loadContacts, { immediate: true })
</script>
