<template>
	<ion-page>
		<ion-header>
			<ion-toolbar>
				<ion-buttons slot="start">
					<ion-back-button
						:default-href="backHref"
						text="Back"
					/>
				</ion-buttons>
				<ion-title>Contact</ion-title>
				<ion-buttons slot="end">
					<ion-button @click="reportOpen = true">
						<ion-icon :icon="flagOutline" slot="start" />
						Report
					</ion-button>
				</ion-buttons>
			</ion-toolbar>
		</ion-header>

		<ion-content class="ion-padding">
			<div v-if="loading && !contact" class="py-12 text-center text-slate-500 text-sm">
				Loading…
			</div>

			<template v-else-if="contact">
				<div v-if="contact.upload_file" class="mb-4">
					<a
						v-if="isImagePreview"
						:href="contact.upload_file"
						target="_blank"
						rel="noopener"
						class="block overflow-hidden rounded-2xl border border-slate-200 bg-slate-50"
					>
						<img
							:src="contact.upload_file"
							alt="Scanned business card"
							class="w-full max-h-48 object-contain bg-white"
						/>
					</a>
					<div
						v-else
						class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700"
					>
						<a
							:href="contact.upload_file"
							target="_blank"
							rel="noopener"
							class="text-blue-600 font-medium"
						>
							Open scanned PDF
						</a>
						<span class="text-slate-500"> to double-check printed details</span>
					</div>
				</div>

				<div class="contact-card mb-4">
					<h1 class="text-xl font-semibold text-slate-900">
						{{ contact.display_name }}
					</h1>
					<p
						v-if="contact.job_title || contact.organization_name"
						class="text-sm text-slate-600 mt-1"
					>
						<span v-if="contact.job_title">{{ contact.job_title }}</span>
						<span v-if="contact.job_title && contact.organization_name"> at </span>
						<span v-if="contact.organization_name">{{
							contact.organization_name
						}}</span>
					</p>
				</div>

				<div class="space-y-3 mb-8">
					<a
						v-if="contact.email"
						:href="`mailto:${primaryMailto}`"
						class="contact-card flex items-center gap-3 no-underline text-inherit"
					>
						<div
							class="h-10 w-10 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center"
						>
							<ion-icon :icon="mailOutline" />
						</div>
						<div class="min-w-0">
							<div class="text-xs text-slate-500">Email</div>
							<div class="font-medium break-words">{{ contact.email }}</div>
						</div>
					</a>

					<a
						v-if="contact.mobile_no"
						:href="`tel:${contact.mobile_no}`"
						class="contact-card flex items-center gap-3 no-underline text-inherit"
					>
						<div
							class="h-10 w-10 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center"
						>
							<ion-icon :icon="callOutline" />
						</div>
						<div class="min-w-0">
							<div class="text-xs text-slate-500">Mobile</div>
							<div class="font-medium">{{ contact.mobile_no }}</div>
						</div>
					</a>

					<a
						v-if="contact.phone_no"
						:href="`tel:${contact.phone_no}`"
						class="contact-card flex items-center gap-3 no-underline text-inherit"
					>
						<div
							class="h-10 w-10 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center"
						>
							<ion-icon :icon="callOutline" />
						</div>
						<div class="min-w-0">
							<div class="text-xs text-slate-500">Landline</div>
							<div class="font-medium">{{ contact.phone_no }}</div>
						</div>
					</a>

					<div
						v-if="contact.website"
						class="contact-card flex items-center gap-3"
					>
						<div
							class="h-10 w-10 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center"
						>
							<ion-icon :icon="globeOutline" />
						</div>
						<div class="min-w-0">
							<div class="text-xs text-slate-500">Website</div>
							<div class="font-medium truncate">{{ contact.website }}</div>
						</div>
					</div>

					<a
						v-if="contact.address_display"
						:href="mapsUrl(contact.address_display)"
						target="_blank"
						rel="noopener"
						class="contact-card flex items-center gap-3 no-underline text-inherit"
					>
						<div
							class="h-10 w-10 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center"
						>
							<ion-icon :icon="locationOutline" />
						</div>
						<div class="min-w-0">
							<div class="text-xs text-slate-500">Address</div>
							<div class="font-medium break-words">
								{{ contact.address_display }}
							</div>
							<div
								v-if="addressParts"
								class="text-xs text-slate-500 mt-1"
							>
								{{ addressParts }}
							</div>
						</div>
					</a>
				</div>

				<div class="mb-6">
					<div class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
						CRM handoff
					</div>
					<div class="contact-card mb-3">
						<div class="flex items-center justify-between gap-2">
							<span class="text-sm font-medium text-slate-900">
								{{ contact.handoff_status || "Draft" }}
							</span>
							<span
								v-if="handoff?.readiness?.score != null"
								class="text-xs text-slate-500"
							>
								Score {{ handoff.readiness.score }}
							</span>
						</div>
						<p
							v-if="partyHint"
							class="text-sm text-blue-800 mt-2 leading-snug"
						>
							{{ partyHint }}
						</p>
						<ul
							v-if="(handoff?.readiness?.blockers || []).length"
							class="mt-2 text-sm text-red-700 list-disc pl-4 space-y-0.5"
						>
							<li
								v-for="(b, i) in handoff.readiness.blockers"
								:key="'b' + i"
							>
								{{ b }}
							</li>
						</ul>
						<ul
							v-if="(handoff?.matches || []).length"
							class="mt-2 text-xs text-slate-600 space-y-1"
						>
							<li
								v-for="(m, i) in handoff.matches.slice(0, 5)"
								:key="'m' + i"
							>
								{{ m.doctype }} · {{ m.title || m.name }} ({{ m.score }})
							</li>
						</ul>
						<div
							v-if="contact.erpnext_lead"
							class="mt-2 flex items-center gap-2 text-sm text-emerald-700"
						>
							<span class="min-w-0 break-words">
								Lead {{ contact.erpnext_lead }}
								<span v-if="contact.erpnext_customer">
									· Customer {{ contact.erpnext_customer }}
								</span>
							</span>
							<a
								:href="deskLeadUrl"
								target="_blank"
								rel="noopener"
								class="shrink-0 text-emerald-700"
								:title="`Open ${contact.erpnext_lead} in Desk`"
								@click.stop
							>
								<ion-icon :icon="openOutline" class="text-lg" />
							</a>
						</div>
					</div>

					<div
						v-if="canCreateCrm"
						class="space-y-2"
					>
						<button
							v-if="needsImprove"
							type="button"
							class="w-full rounded-2xl bg-slate-900 text-white py-3.5 px-4 font-semibold text-base active:bg-slate-800 disabled:opacity-50"
							:disabled="handoffBusy"
							@click="openImproveDialog"
						>
							Improve & create
						</button>
						<button
							v-else
							type="button"
							class="w-full rounded-2xl bg-slate-900 text-white py-3.5 px-4 font-semibold text-base active:bg-slate-800 disabled:opacity-50"
							:disabled="handoffBusy"
							@click="createCrm(false)"
						>
							{{ createButtonLabel }}
						</button>
						<button
							v-if="handoff?.handoff_status === 'Possible Duplicate'"
							type="button"
							class="w-full rounded-2xl border border-slate-300 bg-white text-slate-800 py-3 px-4 font-medium text-sm active:bg-slate-50 disabled:opacity-50"
							:disabled="handoffBusy"
							@click="createCrm(true)"
						>
							Create anyway
						</button>
						<button
							v-if="needsImprove"
							type="button"
							class="w-full rounded-2xl border border-slate-300 bg-white text-slate-800 py-3 px-4 font-medium text-sm active:bg-slate-50 disabled:opacity-50"
							:disabled="handoffBusy"
							@click="createCrm(hasStrongMatches)"
						>
							{{ createButtonLabel }} anyway
						</button>
						<button
							type="button"
							class="w-full rounded-2xl border border-slate-200 text-slate-600 py-2.5 px-4 text-sm active:bg-slate-50 disabled:opacity-50"
							:disabled="handoffBusy"
							@click="skipCrm"
						>
							Skip for now
						</button>
					</div>
				</div>

				<ion-modal
					:is-open="improveOpen"
					@didDismiss="improveOpen = false"
				>
					<ion-header>
						<ion-toolbar>
							<ion-title>Improve data</ion-title>
							<ion-buttons slot="end">
								<ion-button @click="improveOpen = false">Close</ion-button>
							</ion-buttons>
						</ion-toolbar>
					</ion-header>
					<ion-content class="ion-padding">
						<p class="text-sm text-slate-600 mb-4">
							Score {{ handoff?.readiness?.score ?? "—" }} — auto-create needs
							{{ handoff?.auto_create_min_score ?? 95 }}+. Add missing details, then
							create.
						</p>
						<div class="space-y-3 mb-6">
							<label
								v-for="field in improveFields"
								:key="field.key"
								class="block"
							>
								<span class="text-xs font-medium text-slate-600">
									{{ field.label }}
									<span v-if="field.reqd" class="text-red-600">*</span>
								</span>
								<input
									v-model="improveValues[field.key]"
									type="text"
									class="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm"
									:placeholder="field.label"
								/>
							</label>
						</div>
						<button
							type="button"
							class="w-full rounded-2xl bg-slate-900 text-white py-3.5 px-4 font-semibold disabled:opacity-50"
							:disabled="handoffBusy"
							@click="submitImprove"
						>
							Save & create
						</button>
						<p v-if="improveError" class="text-sm text-red-600 mt-3">{{ improveError }}</p>
					</ion-content>
				</ion-modal>

				<button
					type="button"
					class="w-full rounded-2xl bg-slate-900 text-white py-4 px-4 font-semibold text-base active:bg-slate-800 flex items-center justify-center gap-2"
					@click="suggestAppointment"
				>
					<ion-icon :icon="calendarOutline" class="text-xl" />
					Suggest appointment
				</button>
				<p class="text-xs text-slate-500 text-center mt-2 px-4 leading-relaxed">
					Demo only — scheduling will connect to your calendar later.
				</p>
			</template>

			<p v-if="error" class="text-sm text-red-600 mt-4">{{ error }}</p>

			<ReportIssueModal
				:is-open="reportOpen"
				:slug="props.name"
				:import-name="contact?.lead_data_import || ''"
				@close="reportOpen = false"
				@created="onIssueCreated"
			/>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { computed, inject, onMounted, ref } from "vue"
import {
	IonPage,
	IonHeader,
	IonToolbar,
	IonTitle,
	IonContent,
	IonButtons,
	IonBackButton,
	IonButton,
	IonIcon,
	IonModal,
	alertController,
} from "@ionic/vue"
import {
	mailOutline,
	callOutline,
	globeOutline,
	locationOutline,
	calendarOutline,
	openOutline,
	flagOutline,
} from "ionicons/icons"
import { createResource } from "frappe-ui"
import ReportIssueModal from "@/components/ReportIssueModal.vue"

const props = defineProps({
	name: { type: String, required: true },
})

const toast = inject("$toast")
const contact = ref(null)
const loading = ref(false)
const error = ref("")
const handoffBusy = ref(false)
const improveOpen = ref(false)
const improveFields = ref([])
const improveValues = ref({})
const improveError = ref("")
const reportOpen = ref(false)

const backHref = computed(() => {
	const importName = contact.value?.lead_data_import
	return importName ? `/scan/detail/${importName}` : "/scan/home"
})

const handoff = computed(() => contact.value?.handoff || {})
const partyHint = computed(() => handoff.value?.party_hint?.message || "")
const canCreateCrm = computed(() => {
	const status = contact.value?.handoff_status || "Draft"
	return !["Created", "Skipped", "Linked"].includes(status)
})
const needsImprove = computed(() => !!handoff.value?.needs_improve)
const hasStrongMatches = computed(() =>
	(handoff.value?.matches || []).some((m) => (m.score || 0) >= 85)
)
const createButtonLabel = computed(() => {
	if (handoff.value?.party_hint?.customer) {
		return "Create Converted Lead"
	}
	if (handoff.value?.party_hint?.supplier) {
		return "Create Lead (link Supplier)"
	}
	return "Create Lead + Contact"
})

const deskLeadUrl = computed(() => {
	const lead = contact.value?.erpnext_lead
	return lead ? `/app/lead/${encodeURIComponent(lead)}` : "#"
})

const primaryMailto = computed(() => {
	const raw = contact.value?.email || ""
	return raw.split(",")[0].trim()
})

const isImagePreview = computed(() => {
	const url = (contact.value?.upload_file || "").toLowerCase()
	if (!url) return false
	if (url.includes(".pdf")) return false
	return (
		url.includes(".png") ||
		url.includes(".jpg") ||
		url.includes(".jpeg") ||
		url.includes(".webp") ||
		url.includes(".gif") ||
		url.includes(".heic") ||
		!url.includes(".")
	)
})

const addressParts = computed(() => {
	const c = contact.value
	if (!c) return ""
	const bits = [
		c.address_line_1,
		[c.postal_code, c.city].filter(Boolean).join(" "),
		c.country,
	].filter(Boolean)
	// Avoid duplicating the composed display string when parts are incomplete.
	if (bits.length <= 1) return ""
	const composed = bits.join(", ")
	return composed !== c.address_display ? composed : ""
})

const contactResource = createResource({
	url: "phamos.api.scan.get_contact",
	auto: false,
	onSuccess(data) {
		contact.value = data
	},
})

async function load() {
	loading.value = true
	error.value = ""
	try {
		await contactResource.fetch({ name: props.name })
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load contact"
	} finally {
		loading.value = false
	}
}

function mapsUrl(address) {
	return `https://maps.google.com/?q=${encodeURIComponent(address || "")}`
}

async function createCrm(force) {
	handoffBusy.value = true
	error.value = ""
	try {
		const party = handoff.value?.party_hint || {}
		const result = await createResource({
			url: "phamos.api.scan.create_crm_records",
			auto: false,
		}).submit({
			lead_data_name: props.name,
			force: force ? 1 : 0,
			customer: party.customer || "",
			supplier: party.supplier || "",
		})
		toast?.({
			title: "CRM records",
			text: result?.message || "Created",
			icon: "check",
			iconClasses: "text-emerald-600",
		})
		await load()
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not create CRM records"
	} finally {
		handoffBusy.value = false
	}
}

async function skipCrm() {
	handoffBusy.value = true
	try {
		await createResource({
			url: "phamos.api.scan.skip_handoff",
			auto: false,
		}).submit({ lead_data_name: props.name })
		await load()
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not skip"
	} finally {
		handoffBusy.value = false
	}
}

async function openImproveDialog() {
	improveError.value = ""
	handoffBusy.value = true
	try {
		const data = await createResource({
			url: "phamos.api.scan.get_improve_form",
			auto: false,
		}).submit({ lead_data_name: props.name })
		const fields = (data?.fields || []).map((f) => ({
			...f,
			key: `${f.source_doctype}:${f.fieldname}`,
		}))
		improveFields.value = fields
		const values = {}
		for (const f of fields) {
			values[f.key] = f.value || ""
		}
		improveValues.value = values
		improveOpen.value = true
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load improve form"
	} finally {
		handoffBusy.value = false
	}
}

async function submitImprove() {
	improveError.value = ""
	for (const f of improveFields.value) {
		if (f.reqd && !(improveValues.value[f.key] || "").trim()) {
			improveError.value = `${f.label} is required`
			return
		}
	}
	handoffBusy.value = true
	try {
		const result = await createResource({
			url: "phamos.api.scan.update_lead_data_fields",
			auto: false,
		}).submit({
			lead_data_name: props.name,
			values: improveValues.value,
			create_after: 1,
		})
		if (result?.create_error) {
			improveError.value = result.create_error
			await load()
			return
		}
		improveOpen.value = false
		toast?.({
			title: "CRM records",
			text: result?.created?.message || "Saved",
			icon: "check",
			iconClasses: "text-emerald-600",
		})
		await load()
	} catch (e) {
		improveError.value = e?.messages?.[0] || e?.message || "Could not save"
	} finally {
		handoffBusy.value = false
	}
}

function onIssueCreated(result) {
	toast?.({
		title: "Issue reported",
		text: result?.message || result?.name || "Thanks for the feedback",
		icon: "check",
		iconClasses: "text-emerald-600",
	})
}

async function suggestAppointment() {
	const who = contact.value?.display_name || "this contact"
	const alert = await alertController.create({
		header: "Suggest appointment",
		message: `We'll propose a meeting with ${who} based on calendar availability. Coming soon — this is a demo preview.`,
		buttons: ["Nice!"],
	})
	await alert.present()
	toast?.({
		title: "Appointment suggestion",
		text: "Simulated for the demo",
		icon: "calendar",
		iconClasses: "text-blue-600",
	})
}

onMounted(load)
</script>
