<template>
	<ion-page>
		<ion-header>
			<ion-toolbar>
				<ion-title>Issues</ion-title>
				<ion-buttons slot="end">
					<ion-button @click="session.logout.submit()">
						<ion-icon :icon="logOutOutline" slot="icon-only" />
					</ion-button>
				</ion-buttons>
			</ion-toolbar>
		</ion-header>

		<ion-content class="ion-padding">
			<div class="mb-4">
				<h1 class="text-2xl font-semibold text-slate-900 tracking-tight">
					Lead Scan issues
				</h1>
				<p class="text-sm text-slate-600 mt-1 leading-relaxed">
					Feedback filed from the field. Tap a row to open it in Desk.
				</p>
			</div>

			<div class="flex items-center justify-between mb-3">
				<div class="flex gap-2">
					<button
						type="button"
						class="rounded-full px-3 py-1.5 text-xs font-medium border"
						:class="
							statusGroup === 'open'
								? 'bg-slate-900 text-white border-slate-900'
								: 'bg-white text-slate-600 border-slate-200'
						"
						@click="setStatusGroup('open')"
					>
						Open
					</button>
					<button
						type="button"
						class="rounded-full px-3 py-1.5 text-xs font-medium border"
						:class="
							statusGroup === 'closed'
								? 'bg-slate-900 text-white border-slate-900'
								: 'bg-white text-slate-600 border-slate-200'
						"
						@click="setStatusGroup('closed')"
					>
						Closed
					</button>
				</div>
				<button
					type="button"
					class="text-sm text-blue-600 font-medium"
					:disabled="loading"
					@click="refresh"
				>
					Refresh
				</button>
			</div>

			<input
				v-model="search"
				type="search"
				placeholder="Search issues…"
				class="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm mb-3"
				@keyup.enter="refresh"
			/>

			<p v-if="error" class="text-sm text-red-600 mb-3">{{ error }}</p>

			<div
				v-if="loading && !issues.length"
				class="py-10 text-center text-slate-500 text-sm"
			>
				Loading issues…
			</div>
			<div
				v-else-if="!issues.length"
				class="rounded-2xl border border-dashed border-slate-300 bg-white/60 p-5 text-center text-sm text-slate-600"
			>
				No {{ statusGroup }} Lead Scan issues.
			</div>
			<ul v-else class="space-y-3 pb-24">
				<li
					v-for="issue in issues"
					:key="issue.name"
					class="contact-card"
				>
					<a
						:href="`/app/issue/${encodeURIComponent(issue.name)}`"
						target="_blank"
						rel="noopener"
						class="block no-underline text-inherit active:opacity-80"
					>
						<div class="flex items-start justify-between gap-3">
							<div class="min-w-0">
								<div class="font-medium text-slate-900 truncate">
									{{ issue.subject }}
								</div>
								<div class="text-xs text-slate-500 mt-0.5">
									{{ issue.name }}
								</div>
								<div class="text-xs text-slate-500 mt-1">
									{{ issue.age_label }}
								</div>
							</div>
							<StatusBadge :status="issue.status" />
						</div>
					</a>
				</li>
			</ul>

			<button
				v-if="hasMore"
				type="button"
				class="mb-24 w-full rounded-2xl border border-slate-300 bg-white py-3 text-sm font-medium text-slate-800 active:bg-slate-50 disabled:opacity-50"
				:disabled="loadingMore"
				@click="loadMore"
			>
				{{ loadingMore ? "Loading…" : "Load more" }}
			</button>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { inject, onMounted, ref, watch } from "vue"
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
import { logOutOutline } from "ionicons/icons"
import { createResource } from "frappe-ui"
import StatusBadge from "@/components/StatusBadge.vue"

const PAGE_SIZE = 20

const session = inject("$session")
const issues = ref([])
const loading = ref(false)
const loadingMore = ref(false)
const hasMore = ref(false)
const statusGroup = ref("open")
const search = ref("")
const error = ref("")
const nextStart = ref(0)
let searchTimer = null

async function fetchPage({ start = 0, append = false } = {}) {
	const data = await createResource({
		url: "phamos.api.scan.list_scan_issues",
		auto: false,
	}).submit({
		status_group: statusGroup.value,
		search: search.value.trim(),
		limit: PAGE_SIZE,
		start,
	})
	const rows = data?.issues || []
	hasMore.value = !!data?.has_more
	nextStart.value = start + rows.length
	if (append) {
		issues.value = [...issues.value, ...rows]
	} else {
		issues.value = rows
	}
}

async function refresh() {
	loading.value = true
	error.value = ""
	try {
		await fetchPage({ start: 0, append: false })
	} catch (e) {
		issues.value = []
		hasMore.value = false
		error.value = e?.messages?.[0] || e?.message || "Could not load issues"
	} finally {
		loading.value = false
	}
}

async function loadMore() {
	if (!hasMore.value || loadingMore.value) return
	loadingMore.value = true
	error.value = ""
	try {
		await fetchPage({ start: nextStart.value, append: true })
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not load more"
	} finally {
		loadingMore.value = false
	}
}

function setStatusGroup(group) {
	statusGroup.value = group
	refresh()
}

watch(search, () => {
	clearTimeout(searchTimer)
	searchTimer = setTimeout(refresh, 300)
})

onMounted(refresh)
</script>
