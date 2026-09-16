<template>
	<Dialog
		:options="{ title: contact?.full_name || 'Contact', size: 'lg' }"
		:model-value="modelValue"
		@update:model-value="emit('update:modelValue', $event)"
	>
		<template #body-content>
			<div v-if="contact" class="space-y-3">
				<div class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-7">
					<Badge v-if="contact.is_primary" label="Primary" theme="green" size="sm" variant="subtle" />
					<span v-if="contact.designation">{{ contact.designation }}</span>
					<span v-if="contact.department" class="text-ink-gray-5">· {{ contact.department }}</span>
					<span v-if="contact.company_name" class="text-ink-gray-5">· {{ contact.company_name }}</span>
				</div>

				<div v-if="contact.emails.length">
					<div class="mb-1 text-xs text-ink-gray-5">Email</div>
					<div class="space-y-0.5">
						<button
							v-for="email in contact.emails"
							:key="email"
							type="button"
							class="flex items-center gap-1.5 text-sm text-ink-gray-8 hover:text-ink-gray-9"
							title="Write an email"
							@click="emit('compose', email)"
						>
							<FeatherIcon name="mail" class="h-3.5 w-3.5 flex-none text-ink-gray-5" />
							<span>{{ email }}</span>
						</button>
					</div>
				</div>

				<div v-if="contact.phones.length">
					<div class="mb-1 text-xs text-ink-gray-5">Phone</div>
					<div class="space-y-0.5">
						<!-- Same as the header numbers: dialling opens the call-note dialog. -->
						<a
							v-for="number in contact.phones"
							:key="number"
							:href="`tel:${number}`"
							class="flex items-center gap-1.5 text-sm text-ink-gray-8 hover:text-ink-gray-9"
							@click="emit('call')"
						>
							<FeatherIcon name="phone" class="h-3.5 w-3.5 flex-none text-ink-gray-5" />
							<span>{{ number }}</span>
						</a>
					</div>
				</div>

				<!-- The details in the header belong to nobody on file, so promoting
				     someone would drop them. Ask before that happens. -->
				<div
					v-if="decision"
					class="rounded-md border border-outline-amber-2 bg-surface-amber-1 p-3 text-sm text-ink-gray-8"
				>
					<p class="font-medium">The current contact details aren't saved as a contact.</p>
					<p class="mt-1 text-xs text-ink-gray-7">
						{{ decisionSummary }}
					</p>
					<div class="mt-2 flex flex-wrap gap-2">
						<Button variant="solid" :loading="saving" @click="setPrimary('create')">
							Create a contact from them
						</Button>
						<Button variant="subtle" :loading="saving" @click="setPrimary('discard')">
							Discard them
						</Button>
						<Button variant="ghost" @click="decision = null">Cancel</Button>
					</div>
				</div>

				<ErrorMessage :message="error" />

				<div class="flex items-center gap-2 pt-1">
					<Button
						v-if="!contact.is_primary && !decision"
						variant="solid"
						:loading="saving"
						@click="setPrimary()"
					>
						Set as main contact
					</Button>
					<a
						:href="`/app/contact/${encodeURIComponent(contact.name)}`"
						target="_blank"
						rel="noopener"
						class="ml-auto text-xs text-ink-gray-6 hover:text-ink-gray-9"
					>
						Open in Desk
					</a>
				</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { call } from "frappe-ui"

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	lead: { type: Object, required: true },
	contact: { type: Object, default: null },
})

const emit = defineEmits(["update:modelValue", "changed", "compose", "call"])

const saving = ref(false)
const error = ref("")
/** The details that would be lost, once the backend says it needs an answer. */
const decision = ref(null)

const decisionSummary = computed(() => {
	const current = decision.value || {}
	return [current.lead_name, current.email_id, current.mobile_no, current.phone]
		.filter(Boolean)
		.join(" · ")
})

async function setPrimary(untrackedAction) {
	error.value = ""
	saving.value = true
	try {
		const result = await call("phamos.api.sales_leads.set_lead_primary_contact", {
			lead: props.lead.name,
			contact: props.contact.name,
			untracked_action: untrackedAction || null,
		})
		if (result.needs_decision) {
			decision.value = result.current
			return
		}
		emit("changed", result.lead)
		emit("update:modelValue", false)
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not change the main contact"
	} finally {
		saving.value = false
	}
}

watch(
	() => props.modelValue,
	(open) => {
		if (!open) return
		error.value = ""
		decision.value = null
	}
)
</script>
