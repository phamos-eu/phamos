<template>
	<ion-page>
		<ion-header>
			<ion-toolbar>
				<ion-title>Lead Scan</ion-title>
				<ion-buttons slot="end">
					<ion-button @click="session.logout.submit()">
						<ion-icon :icon="logOutOutline" slot="icon-only" />
					</ion-button>
				</ion-buttons>
			</ion-toolbar>
		</ion-header>

		<ion-content class="ion-padding">
			<div class="mb-5">
				<p class="text-sm text-slate-500 mb-1">
					Signed in as {{ session.fullName }}
				</p>
				<h1 class="text-2xl font-semibold text-slate-900 tracking-tight">
					Business card scanner
				</h1>
				<p class="text-sm text-slate-600 mt-1 leading-relaxed">
					Scan a card with your iPhone Document Scanner. AI extracts name,
					email, and phone automatically.
				</p>
			</div>

			<button
				type="button"
				class="w-full rounded-2xl bg-blue-600 text-white py-4 px-4 font-semibold text-base shadow-sm active:bg-blue-700 disabled:opacity-60 flex items-center justify-center gap-2"
				:disabled="uploading"
				@click="triggerPicker"
			>
				<ion-icon :icon="scanOutline" class="text-xl" />
				{{ uploading ? "Uploading…" : "Scan business card" }}
			</button>

			<input
				ref="fileInput"
				type="file"
				class="hidden"
				accept="application/pdf,image/*"
				@change="onFileSelected"
			/>

			<p class="text-xs text-slate-500 mt-2 text-center leading-relaxed px-2">
				Choose <strong>Scan Documents</strong> or Photos — do not use a forced
				camera capture so iOS can offer the document scanner.
			</p>

			<p v-if="error" class="mt-3 text-sm text-red-600">{{ error }}</p>

			<div class="mt-8 flex items-center justify-between">
				<h2 class="text-sm font-semibold text-slate-700 uppercase tracking-wide">
					Recent scans
				</h2>
				<button
					type="button"
					class="text-sm text-blue-600 font-medium"
					:disabled="loading"
					@click="loadScans"
				>
					Refresh
				</button>
			</div>

			<div v-if="loading && !scans.length" class="py-10 text-center text-slate-500 text-sm">
				Loading…
			</div>

			<div
				v-else-if="!scans.length"
				class="mt-4 rounded-2xl border border-dashed border-slate-300 bg-white/60 p-6 text-center"
			>
				<p class="text-sm text-slate-600">No scans yet. Start with a business card.</p>
			</div>

			<ul v-else class="mt-3 space-y-3 pb-8">
				<li
					v-for="scan in scans"
					:key="scan.name"
					class="contact-card active:bg-slate-50 cursor-pointer"
					@click="openScan(scan.name)"
				>
					<div class="flex items-start justify-between gap-3">
						<div class="min-w-0">
							<div class="font-medium text-slate-900 truncate">{{ scan.name }}</div>
							<div class="text-xs text-slate-500 mt-0.5">
								{{ formatRelativeTime(scan.modified) }}
								<span v-if="scan.input_type"> · {{ scan.input_type }}</span>
								<span v-if="scan.contact_count">
									· {{ scan.contact_count }}
									{{ scan.contact_count === 1 ? "contact" : "contacts" }}
								</span>
							</div>
						</div>
						<StatusBadge :status="scan.status" />
					</div>
				</li>
			</ul>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { inject, onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import {
	IonPage,
	IonHeader,
	IonToolbar,
	IonTitle,
	IonContent,
	IonButtons,
	IonButton,
	IonIcon,
} from "@ionic/vue"
import { logOutOutline, scanOutline } from "ionicons/icons"
import { createResource } from "frappe-ui"
import StatusBadge from "@/components/StatusBadge.vue"
import { fileToBase64, formatRelativeTime } from "@/utils/upload"

const session = inject("$session")
const toast = inject("$toast")
const router = useRouter()

const fileInput = ref(null)
const scans = ref([])
const loading = ref(false)
const uploading = ref(false)
const error = ref("")

const listResource = createResource({
	url: "phamos.api.scan.list_scans",
	auto: false,
	onSuccess(data) {
		scans.value = data || []
	},
})

async function loadScans() {
	loading.value = true
	error.value = ""
	try {
		await listResource.fetch({ limit: 40 })
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load scans"
	} finally {
		loading.value = false
	}
}

function triggerPicker() {
	error.value = ""
	fileInput.value?.click()
}

async function onFileSelected(event) {
	const input = event.target
	const file = input.files?.[0]
	if (!file) return

	uploading.value = true
	error.value = ""
	try {
		// Read before clearing the input — clearing first breaks FileReader on iOS Safari
		const content = await fileToBase64(file)
		const filename = file.name || "scan.pdf"
		input.value = ""

		const create = createResource({
			url: "phamos.api.scan.create_scan",
			auto: false,
		})
		const result = await create.submit({
			filename,
			content,
		})
		toast?.({
			title: "Scan uploaded",
			text: "AI processing started",
			icon: "check",
			iconClasses: "text-green-600",
		})
		await router.push({ name: "ScanDetail", params: { name: result.name } })
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Upload failed"
		toast?.({
			title: "Upload failed",
			text: error.value,
			icon: "alert-circle",
			iconClasses: "text-red-600",
		})
	} finally {
		uploading.value = false
		// Ensure input can be reused even if read failed mid-way
		if (input && input.value) input.value = ""
	}
}

function openScan(name) {
	router.push({ name: "ScanDetail", params: { name } })
}

onMounted(loadScans)
</script>
