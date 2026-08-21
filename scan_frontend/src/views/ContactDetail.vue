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
	IonIcon,
	alertController,
} from "@ionic/vue"
import {
	mailOutline,
	callOutline,
	globeOutline,
	locationOutline,
	calendarOutline,
} from "ionicons/icons"
import { createResource } from "frappe-ui"

const props = defineProps({
	name: { type: String, required: true },
})

const toast = inject("$toast")
const contact = ref(null)
const loading = ref(false)
const error = ref("")

const backHref = computed(() => {
	const importName = contact.value?.lead_data_import
	return importName ? `/scan/detail/${importName}` : "/scan/home"
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
