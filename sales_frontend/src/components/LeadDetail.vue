<template>
	<div class="flex h-full min-h-0 w-full flex-1 flex-col overflow-y-auto p-5 text-ink-gray-9">
		<div class="mb-4">
			<div class="flex items-center gap-2">
				<span class="text-xs font-normal text-ink-gray-5">{{ lead.name }}</span>
				<Badge :label="lead.status" :theme="statusTheme(lead.status)" size="sm" variant="subtle" />
			</div>
			<h1 class="mt-0.5 text-lg font-bold tracking-tight text-ink-gray-9">
				{{ lead.lead_name || lead.name }}
			</h1>
			<p v-if="lead.company_name" class="text-sm text-ink-gray-6">{{ lead.company_name }}</p>
		</div>

		<section class="mb-5 space-y-2">
			<h2 class="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Contact</h2>
			<a
				v-for="number in phoneNumbers"
				:key="number"
				:href="`tel:${number}`"
				class="flex items-center gap-2 rounded-md border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 hover:bg-surface-gray-2"
				@click="onPhoneClick"
			>
				<FeatherIcon name="phone" class="h-4 w-4 flex-shrink-0 text-ink-gray-5" />
				<span>{{ number }}</span>
			</a>
			<a
				v-if="lead.email_id"
				:href="mailtoHref"
				class="flex items-center gap-2 rounded-md border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 hover:bg-surface-gray-2"
			>
				<FeatherIcon name="mail" class="h-4 w-4 flex-shrink-0 text-ink-gray-5" />
				<span>{{ lead.email_id }}</span>
			</a>
		</section>

		<section class="mb-5">
			<div class="mb-2 flex items-center justify-between">
				<h2 class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Notes</h2>
				<Button variant="subtle" size="sm" @click="showNoteDialog = true">Add note</Button>
			</div>
			<div v-if="!lead.notes?.length" class="text-sm text-ink-gray-5">No notes yet.</div>
			<div v-else class="space-y-3">
				<div
					v-for="note in lead.notes"
					:key="note.name"
					class="rounded-md border border-outline-gray-2 bg-surface-white px-3 py-2"
				>
					<div class="mb-1 flex items-center gap-2 text-xs text-ink-gray-5">
						<span class="font-medium text-ink-gray-7">{{ note.added_by_name || note.added_by }}</span>
						<span>{{ formatDatetime(note.added_on) }}</span>
					</div>
					<div class="whitespace-pre-wrap text-sm text-ink-gray-8">{{ stripHtml(note.note) }}</div>
				</div>
			</div>
		</section>

		<section>
			<h2 class="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
				Last communication
			</h2>
			<div v-if="!lead.communications?.length" class="text-sm text-ink-gray-5">
				No communication logged yet.
			</div>
			<div v-else class="space-y-3">
				<div
					v-for="comm in lead.communications"
					:key="comm.name"
					class="rounded-md border border-outline-gray-2 bg-surface-white px-3 py-2"
				>
					<div class="mb-1 flex items-center gap-2 text-xs text-ink-gray-5">
						<Badge
							:label="comm.sent_or_received === 'Sent' ? 'Sent' : 'Received'"
							:theme="comm.sent_or_received === 'Sent' ? 'blue' : 'green'"
							size="sm"
							variant="subtle"
						/>
						<span>{{ formatDatetime(comm.communication_date) }}</span>
					</div>
					<div class="text-sm font-medium text-ink-gray-9">{{ comm.subject || "(no subject)" }}</div>
					<div class="mt-0.5 truncate text-xs text-ink-gray-6">{{ stripHtml(comm.content) }}</div>
				</div>
			</div>
		</section>
	</div>

	<Teleport v-if="propertiesHostReady" to="#lead-properties-host">
		<div class="flex h-full min-h-0 flex-col bg-surface-white text-ink-gray-9">
			<div class="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-4">
				<section class="space-y-3 text-sm">
					<div>
						<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Owner</div>
						<div class="text-ink-gray-8">{{ lead.lead_owner_name || lead.lead_owner || "—" }}</div>
					</div>
					<div>
						<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Source</div>
						<div class="text-ink-gray-8">{{ lead.source || "—" }}</div>
					</div>
					<div>
						<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">Territory</div>
						<div class="text-ink-gray-8">{{ lead.territory || "—" }}</div>
					</div>
					<div>
						<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
							Next Follow Up
						</div>
						<div class="flex items-center gap-2">
							<span class="text-ink-gray-8">
								{{ lead.custom_next_followup ? formatDatetime(lead.custom_next_followup) : "Not set" }}
							</span>
							<Button variant="subtle" size="sm" @click="showNoteDialog = true">Edit</Button>
						</div>
					</div>
					<div v-if="lead.custom_status_comment">
						<div class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-6">
							Status Comment
						</div>
						<div class="whitespace-pre-wrap text-ink-gray-8">{{ lead.custom_status_comment }}</div>
					</div>
				</section>
			</div>
			<div class="mt-auto flex-shrink-0 space-y-2 border-t border-outline-gray-2 p-4">
				<a
					:href="lead.desk_url"
					class="flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm font-medium text-ink-gray-7 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				>
					<FeatherIcon name="external-link" class="h-4 w-4 flex-shrink-0" />
					<span class="truncate">Open in Desk</span>
				</a>
			</div>
		</div>
	</Teleport>

	<AddLeadNoteDialog v-model="showNoteDialog" :lead="lead" @saved="onSaved" />
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from "vue"
import { Badge } from "frappe-ui"
import { formatDatetime } from "@spa/utils/datetime"
import AddLeadNoteDialog from "./AddLeadNoteDialog.vue"

const props = defineProps({
	lead: { type: Object, required: true },
})

const emit = defineEmits(["updated"])

const showNoteDialog = ref(false)
const propertiesHostReady = ref(false)

const phoneNumbers = computed(() => {
	return [...new Set([props.lead.mobile_no, props.lead.phone].filter(Boolean))]
})

const mailtoHref = computed(() => {
	const subject = encodeURIComponent(`Re: ${props.lead.lead_name || props.lead.company_name || props.lead.name}`)
	return `mailto:${props.lead.email_id}?cc=crm@phamos.eu&subject=${subject}`
})

function statusTheme(status) {
	const map = {
		Lead: "gray",
		Open: "blue",
		Replied: "blue",
		Opportunity: "orange",
		Quotation: "orange",
		"Lost Quotation": "gray",
		Interested: "green",
		Converted: "green",
		"Do Not Contact": "red",
	}
	return map[status] || "gray"
}

function stripHtml(value) {
	return String(value || "")
		.replace(/<[^>]*>/g, " ")
		.replace(/\s+/g, " ")
		.trim()
}

function onPhoneClick() {
	// tel: link still navigates; also open the note dialog for call logging.
	showNoteDialog.value = true
}

function onSaved(updated) {
	emit("updated", updated)
}

async function syncPropertiesHost() {
	await nextTick()
	propertiesHostReady.value = !!document.getElementById("lead-properties-host")
}

onMounted(syncPropertiesHost)
</script>
