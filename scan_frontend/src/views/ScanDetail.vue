<template>
	<ion-page>
		<ion-header>
			<ion-toolbar>
				<ion-buttons slot="start">
					<ion-back-button default-href="/scan/home" text="Back" />
				</ion-buttons>
				<ion-title>{{ scan?.name || "Scan" }}</ion-title>
				<ion-buttons slot="end">
					<ion-button :disabled="loading" @click="refresh">
						<ion-icon :icon="refreshOutline" slot="icon-only" />
					</ion-button>
				</ion-buttons>
			</ion-toolbar>
		</ion-header>

		<ion-content class="ion-padding">
			<div v-if="loading && !scan" class="py-12 text-center text-slate-500 text-sm">
				Loading scan…
			</div>

			<template v-else-if="scan">
				<div class="flex items-center justify-between gap-3 mb-3">
					<div>
						<div class="text-xs text-slate-500 uppercase tracking-wide font-semibold">
							AI status
						</div>
						<div class="mt-1">
							<StatusBadge :status="scan.status" />
						</div>
					</div>
					<div class="text-xs text-slate-500 text-right">
						{{ scan.input_type }}
						<div v-if="isProcessing" class="text-blue-600 mt-1">Updating…</div>
					</div>
				</div>

				<div
					v-if="isProcessing"
					class="mb-4 rounded-2xl bg-blue-50 border border-blue-100 px-4 py-3 text-sm text-blue-900"
				>
					{{ statusHint }}
				</div>

				<div v-if="scan.upload_file" class="mb-5">
					<div class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
						Scanned card
					</div>
					<a
						v-if="isImagePreview"
						:href="scan.upload_file"
						target="_blank"
						rel="noopener"
						class="block overflow-hidden rounded-2xl border border-slate-200 bg-slate-50"
					>
						<img
							:src="scan.upload_file"
							alt="Scanned business card"
							class="w-full max-h-56 object-contain bg-white"
						/>
					</a>
					<div
						v-else
						class="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 flex items-center gap-2"
					>
						<ion-icon :icon="documentOutline" class="text-slate-400 text-xl" />
						<span>PDF scan attached — open to verify printed details.</span>
						<a
							:href="scan.upload_file"
							target="_blank"
							rel="noopener"
							class="ml-auto text-blue-600 font-medium"
						>
							Open
						</a>
					</div>
				</div>

				<div class="flex items-center justify-between mb-3">
					<h2 class="text-sm font-semibold text-slate-700 uppercase tracking-wide">
						Contacts
						<span v-if="contacts.length" class="text-slate-400 normal-case">
							({{ contacts.length }})
						</span>
					</h2>
				</div>

				<div
					v-if="!contacts.length"
					class="rounded-2xl border border-dashed border-slate-300 bg-white/70 p-5 text-center text-sm text-slate-600 mb-6"
				>
					{{
						isProcessing
							? "No contacts yet — reading the card…"
							: "No contacts found on this scan."
					}}
				</div>

				<ul v-else class="space-y-4 mb-6">
					<li
						v-for="contact in contacts"
						:key="contact.name"
						class="contact-card"
					>
						<button
							type="button"
							class="w-full text-left active:opacity-80"
							@click="openContact(contact.name)"
						>
							<div class="font-semibold text-slate-900">
								{{ contact.display_name }}
							</div>
							<div
								v-if="contact.organization_name || contact.job_title"
								class="text-xs text-slate-500 mt-0.5"
							>
								<span v-if="contact.job_title">{{ contact.job_title }}</span>
								<span v-if="contact.job_title && contact.organization_name">
									·
								</span>
								<span v-if="contact.organization_name">{{
									contact.organization_name
								}}</span>
							</div>
							<div class="mt-3 space-y-1.5 text-sm">
								<div
									v-if="contact.email"
									class="flex items-start gap-2 text-slate-700"
								>
									<ion-icon
										:icon="mailOutline"
										class="text-slate-400 mt-0.5 shrink-0"
									/>
									<span class="break-words">{{ contact.email }}</span>
								</div>
								<a
									v-if="contact.mobile_no"
									:href="`tel:${contact.mobile_no}`"
									class="flex items-center gap-2 text-slate-700 no-underline"
									@click.stop
								>
									<ion-icon :icon="callOutline" class="text-slate-400" />
									<span>
										<span class="text-xs text-slate-500 mr-1">Mobile</span>
										{{ contact.mobile_no }}
									</span>
								</a>
								<a
									v-if="contact.phone_no"
									:href="`tel:${contact.phone_no}`"
									class="flex items-center gap-2 text-slate-700 no-underline"
									@click.stop
								>
									<ion-icon :icon="callOutline" class="text-slate-400" />
									<span>
										<span class="text-xs text-slate-500 mr-1">Landline</span>
										{{ contact.phone_no }}
									</span>
								</a>
								<a
									v-if="contact.address_display"
									:href="mapsUrl(contact.address_display)"
									target="_blank"
									rel="noopener"
									class="flex items-start gap-2 text-slate-700 no-underline"
									@click.stop
								>
									<ion-icon
										:icon="locationOutline"
										class="text-slate-400 mt-0.5 shrink-0"
									/>
									<span class="break-words">{{ contact.address_display }}</span>
								</a>
								<div
									v-if="
										!contact.email &&
										!contact.mobile_no &&
										!contact.phone_no &&
										!contact.address_display
									"
									class="text-xs text-slate-400"
								>
									No email, phone, or address yet
								</div>
							</div>
						</button>

						<div
							v-if="(contact.secondary_contacts || []).length"
							class="mt-4 pt-3 border-t border-slate-100"
						>
							<div class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
								Company contacts
							</div>
							<div class="space-y-2">
								<div
									v-for="(person, idx) in contact.secondary_contacts"
									:key="idx"
									class="rounded-xl bg-slate-50 px-3 py-2"
								>
									<div class="text-sm font-medium text-slate-900">
										{{ person.display_name || "Contact" }}
									</div>
									<p
										v-if="person.designation"
										class="text-xs text-slate-500 mt-0.5"
									>
										{{ person.designation }}
									</p>
									<p
										v-if="person.email"
										class="text-sm text-slate-700 mt-1 break-words"
									>
										{{ person.email }}
									</p>
									<p
										v-if="person.mobile_no"
										class="text-sm text-slate-700"
									>
										<span class="text-xs text-slate-500 mr-1">Mobile</span>
										{{ person.mobile_no }}
									</p>
									<p
										v-if="person.phone_no || (person.phone && person.phone !== person.mobile_no)"
										class="text-sm text-slate-700"
									>
										<span class="text-xs text-slate-500 mr-1">Landline</span>
										{{ person.phone_no || person.phone }}
									</p>
								</div>
							</div>
						</div>
					</li>
				</ul>

				<details class="rounded-2xl border border-slate-200 bg-white mb-8">
					<summary
						class="cursor-pointer select-none px-4 py-3 text-sm font-semibold text-slate-600"
					>
						Processing log
					</summary>
					<div class="log-panel mx-3 mb-3 mt-0">
						{{ scan.status_log || "Waiting for processing…" }}
					</div>
				</details>
			</template>

			<p v-if="error" class="text-sm text-red-600 mt-4">{{ error }}</p>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import {
	IonPage,
	IonHeader,
	IonToolbar,
	IonTitle,
	IonContent,
	IonButtons,
	IonButton,
	IonBackButton,
	IonIcon,
} from "@ionic/vue"
import {
	refreshOutline,
	mailOutline,
	callOutline,
	locationOutline,
	documentOutline,
} from "ionicons/icons"
import { createResource } from "frappe-ui"
import StatusBadge from "@/components/StatusBadge.vue"

const props = defineProps({
	name: { type: String, required: true },
})

const router = useRouter()
const scan = ref(null)
const loading = ref(false)
const error = ref("")
let pollTimer = null

const contacts = computed(() => scan.value?.contacts || [])
const isProcessing = computed(() => {
	const status = scan.value?.status
	return status === "Processing" || status === "Draft"
})

const statusHint = computed(() => {
	if (contacts.value.length) {
		return "Adding company details from the website…"
	}
	return "Reading the business card with AI. Contacts will appear below when ready."
})

const isImagePreview = computed(() => {
	const url = (scan.value?.upload_file || "").toLowerCase()
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

const detailResource = createResource({
	url: "phamos.api.scan.get_scan",
	auto: false,
	onSuccess(data) {
		scan.value = data
	},
})

async function refresh() {
	loading.value = true
	error.value = ""
	try {
		await detailResource.fetch({ name: props.name })
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load scan"
	} finally {
		loading.value = false
	}
}

function startPolling() {
	stopPolling()
	pollTimer = setInterval(() => {
		if (!isProcessing.value) {
			stopPolling()
			return
		}
		detailResource.fetch({ name: props.name }).catch(() => {})
	}, 2000)
}

function stopPolling() {
	if (pollTimer) {
		clearInterval(pollTimer)
		pollTimer = null
	}
}

function openContact(contactName) {
	router.push({ name: "ContactDetail", params: { name: contactName } })
}

function mapsUrl(address) {
	return `https://maps.google.com/?q=${encodeURIComponent(address || "")}`
}

watch(isProcessing, (processing) => {
	if (processing) startPolling()
	else stopPolling()
})

onMounted(async () => {
	await refresh()
	if (isProcessing.value) startPolling()
})

onBeforeUnmount(stopPolling)
</script>
