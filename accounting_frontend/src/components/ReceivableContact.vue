<template>
	<div class="min-w-0">
		<template v-if="contact">
			<div class="truncate text-ink-gray-8" :title="title">{{ contact.name || contact.email || contact.phone }}</div>
			<a
				v-if="contact.email && contact.name"
				:href="`mailto:${contact.email}`"
				class="block truncate text-xs text-ink-gray-5 hover:text-ink-gray-9 hover:underline"
				:title="`Write to ${contact.email}`"
			>
				{{ contact.email }}
			</a>
			<div v-else-if="contact.phone && contact.name" class="truncate text-xs text-ink-gray-5">{{ contact.phone }}</div>
		</template>
		<span v-else class="text-xs text-ink-gray-4">No contact</span>
	</div>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	// {name, email, phone, source} from get_receivables, or null.
	contact: { type: Object, default: null },
})

const SOURCES = {
	invoice: "Contact on the invoice",
	primary_contact: "Primary contact of the customer",
	customer: "Email of the customer",
}

const title = computed(() => {
	const c = props.contact
	if (!c) return ""
	return [c.name, c.email, c.phone, SOURCES[c.source]].filter(Boolean).join(" · ")
})
</script>
