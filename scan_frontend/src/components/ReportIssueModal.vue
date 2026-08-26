<template>
	<ion-modal :is-open="isOpen" @didDismiss="$emit('close')">
		<ion-header>
			<ion-toolbar>
				<ion-title>Report a problem</ion-title>
				<ion-buttons slot="end">
					<ion-button @click="$emit('close')">Close</ion-button>
				</ion-buttons>
			</ion-toolbar>
		</ion-header>
		<ion-content class="ion-padding">
			<p v-if="slug" class="text-xs text-slate-500 mb-3">
				Related:
				<span class="font-mono text-slate-700">{{ slug }}</span>
			</p>
			<p v-else class="text-xs text-slate-500 mb-3">
				General Lead Scan feedback
				<span v-if="importName" class="font-mono text-slate-700">
					· {{ importName }}
				</span>
			</p>

			<div v-if="existing.length" class="mb-4">
				<div class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
					Already reported ({{ existing.length }})
				</div>
				<ul class="space-y-2">
					<li
						v-for="issue in existing"
						:key="issue.name"
						class="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"
					>
						<a
							:href="`/app/issue/${encodeURIComponent(issue.name)}`"
							target="_blank"
							rel="noopener"
							class="text-sm font-medium text-slate-900 no-underline"
						>
							{{ issue.subject }}
						</a>
						<div class="text-xs text-slate-500 mt-0.5">
							{{ issue.status }} · {{ issue.age_label }}
						</div>
					</li>
				</ul>
			</div>

			<label class="block mb-4">
				<span class="text-xs font-medium text-slate-600">What went wrong?</span>
				<textarea
					v-model="text"
					rows="4"
					class="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm"
					placeholder="Brief description…"
				/>
			</label>

			<button
				type="button"
				class="w-full rounded-2xl bg-slate-900 text-white py-3.5 px-4 font-semibold disabled:opacity-50"
				:disabled="busy || !text.trim()"
				@click="submit"
			>
				{{ busy ? "Sending…" : "Submit issue" }}
			</button>
			<p v-if="error" class="text-sm text-red-600 mt-3">{{ error }}</p>
		</ion-content>
	</ion-modal>
</template>

<script setup>
import { ref, watch } from "vue"
import {
	IonModal,
	IonHeader,
	IonToolbar,
	IonTitle,
	IonContent,
	IonButtons,
	IonButton,
} from "@ionic/vue"
import { createResource } from "frappe-ui"

const props = defineProps({
	isOpen: { type: Boolean, default: false },
	slug: { type: String, default: "" },
	importName: { type: String, default: "" },
})

const emit = defineEmits(["close", "created"])

const text = ref("")
const busy = ref(false)
const error = ref("")
const existing = ref([])

watch(
	() => props.isOpen,
	async (open) => {
		if (!open) return
		text.value = ""
		error.value = ""
		existing.value = []
		if (!props.slug) return
		try {
			const data = await createResource({
				url: "phamos.api.scan.list_scan_issues",
				auto: false,
			}).submit({
				lead_data_slug: props.slug,
				status_group: "open",
				limit: 20,
			})
			existing.value = data?.issues || []
		} catch {
			existing.value = []
		}
	}
)

async function submit() {
	error.value = ""
	busy.value = true
	try {
		const result = await createResource({
			url: "phamos.api.scan.create_scan_issue",
			auto: false,
		}).submit({
			description: text.value.trim(),
			lead_data_slug: props.slug || "",
			lead_data_import: props.importName || "",
		})
		emit("created", result)
		emit("close")
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not create issue"
	} finally {
		busy.value = false
	}
}
</script>
