<template>
	<Dialog
		:options="{ title: 'Contacts found in the correspondence', size: '3xl' }"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div class="space-y-3">
				<div v-if="loading" class="flex items-center gap-2 py-8 text-sm text-ink-gray-5">
					<FeatherIcon name="loader" class="h-4 w-4 animate-spin" />
					<span>Reading this lead's emails…</span>
				</div>

				<template v-else>
					<p v-if="messageCount" class="text-xs text-ink-gray-5">
						Read {{ messageCount }} message{{ messageCount === 1 ? "" : "s" }}. Suggestions come
						from an AI reading the correspondence — check them before adding.
					</p>

					<div v-if="!suggestions.length && !error" class="py-8 text-center text-sm text-ink-gray-5">
						No new people found. Everyone in the correspondence is already a contact on this lead.
					</div>

					<div
						v-for="(person, index) in suggestions"
						:key="person.key"
						class="rounded-md border border-outline-gray-2 p-3"
						:class="person.added ? 'bg-surface-gray-1' : ''"
					>
						<div class="grid grid-cols-2 gap-2">
							<FormControl v-model="person.first_name" label="First name" type="text" size="sm" />
							<FormControl v-model="person.last_name" label="Last name" type="text" size="sm" />
							<FormControl v-model="person.email" label="Email" type="text" size="sm" />
							<FormControl v-model="person.phone" label="Phone" type="text" size="sm" />
							<FormControl v-model="person.designation" label="Designation" type="text" size="sm" />
							<FormControl v-model="person.company_name" label="Company" type="text" size="sm" />
						</div>
						<div class="mt-2 flex items-center gap-2">
							<!-- What in the mail made the AI say this, so the user can judge it
							     rather than take it on trust. -->
							<p v-if="person.evidence" class="min-w-0 flex-1 truncate text-xs italic text-ink-gray-5">
								“{{ person.evidence }}”
							</p>
							<span v-else class="flex-1" />
							<Badge v-if="person.added" label="Added" theme="green" size="sm" variant="subtle" />
							<Button
								v-else
								size="sm"
								variant="subtle"
								:loading="person.saving"
								@click="add(person)"
							>
								Add as contact
							</Button>
							<button
								v-if="!person.added"
								type="button"
								class="rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-9"
								title="Dismiss"
								@click="suggestions.splice(index, 1)"
							>
								<FeatherIcon name="x" class="h-3.5 w-3.5" />
							</button>
						</div>
					</div>

					<ErrorMessage :message="error" />
				</template>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { ref, watch } from "vue"
import { call } from "frappe-ui"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	lead: { type: Object, required: true },
})

const emit = defineEmits(["update:modelValue", "added"])

const loading = ref(false)
const error = ref("")
const suggestions = ref([])
const messageCount = ref(0)

async function load() {
	loading.value = true
	error.value = ""
	suggestions.value = []
	try {
		const result = await call("phamos.api.sales_lead_ai.suggest_contacts_from_email", {
			lead: props.lead.name,
		})
		messageCount.value = result.message_count || 0
		suggestions.value = (result.suggestions || []).map((person, index) => ({
			...person,
			// Stable per row: these carry edited form state and get spliced out
			// one at a time, so an index key would re-bind the rows below.
			key: `${person.email || person.first_name || ""}:${index}`,
			saving: false,
			added: false,
		}))
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not read the correspondence"
	} finally {
		loading.value = false
	}
}

async function add(person) {
	person.saving = true
	error.value = ""
	try {
		await call("phamos.api.sales_lead_ai.create_lead_contact", {
			lead: props.lead.name,
			first_name: person.first_name,
			last_name: person.last_name,
			email: person.email,
			phone: person.phone,
			designation: person.designation,
			company_name: person.company_name,
		})
		person.added = true
		emit("added")
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not create the contact"
	} finally {
		person.saving = false
	}
}

watch(
	() => props.modelValue,
	(open) => {
		if (open) load()
	}
)
</script>
