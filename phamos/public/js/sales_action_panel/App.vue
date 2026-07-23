<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import Sidebar from "./components/Sidebar.vue";
import RecordList from "./components/RecordList.vue";
import RecordDetail from "./components/RecordDetail.vue";
import StartWorkModal from "./components/StartWorkModal.vue";
import SettingsPanel from "./components/SettingsPanel.vue";
import { MOCK, SAMPLE_PROJECTS } from "./mockData";

const currentView = ref("leads");
const selectedName = ref(MOCK.leads[0]?.name || null);
const showStartWork = ref(false);
const sidebarOpen = ref(true);

const settings = ref({
	cost_center_project: SAMPLE_PROJECTS[0].name,
	cost_center_project_name: SAMPLE_PROJECTS[0].project_name,
});

const activeSession = ref(null);
const elapsedSeconds = ref(0);
let timerInterval = null;

const counts = computed(() => ({
	leads: MOCK.leads.length,
	opportunities: MOCK.opportunities.length,
	customers: MOCK.customers.length,
	quotations: MOCK.quotations.length,
	contacts: MOCK.contacts.length,
	addresses: MOCK.addresses.length,
}));

const records = computed(() => {
	if (currentView.value === "settings") return [];
	return MOCK[currentView.value] || [];
});

const selectedRecord = computed(() => {
	if (!selectedName.value || currentView.value === "settings") return null;
	return records.value.find((r) => r.name === selectedName.value) || null;
});

const relatedContacts = computed(() => {
	const r = selectedRecord.value;
	if (!r?.contacts) return [];
	return MOCK.contacts.filter((c) => r.contacts.includes(c.name));
});

const relatedAddresses = computed(() => {
	const r = selectedRecord.value;
	const ids = new Set(r?.addresses || []);
	if (r?.contacts) {
		MOCK.contacts
			.filter((c) => r.contacts.includes(c.name))
			.forEach((c) => (c.addresses || []).forEach((a) => ids.add(a)));
	}
	return MOCK.addresses.filter((a) => ids.has(a.name));
});

const relatedQuotations = computed(() => {
	const r = selectedRecord.value;
	if (!r?.quotations) return [];
	return MOCK.quotations.filter((q) => r.quotations.includes(q.name));
});

function changeView(view) {
	currentView.value = view;
	const list = MOCK[view] || [];
	selectedName.value = list[0]?.name || null;
}

function openSettings() {
	currentView.value = "settings";
	selectedName.value = null;
}

function openRelated({ view, name }) {
	currentView.value = view;
	selectedName.value = name;
}

function startTick() {
	clearInterval(timerInterval);
	timerInterval = setInterval(() => {
		if (activeSession.value) elapsedSeconds.value++;
	}, 1000);
}

function stopTick() {
	clearInterval(timerInterval);
	timerInterval = null;
}

function onStartWorkConfirm(payload) {
	showStartWork.value = false;
	activeSession.value = payload;
	elapsedSeconds.value = 0;
	startTick();
	if (typeof frappe !== "undefined") {
		frappe.show_alert({
			message: __("Timesheet started on {0} (click dummy)", [
				payload.project_name || payload.project || "project",
			]),
			indicator: "green",
		});
	}
}

async function loadSettings() {
	if (typeof frappe === "undefined") return;
	try {
		const r = await frappe.call({
			method: "phamos.phamos.page.sales_action_panel.sales_action_panel.get_settings",
		});
		if (r.message?.cost_center_project) {
			settings.value = {
				cost_center_project: r.message.cost_center_project,
				cost_center_project_name:
					r.message.cost_center_project_name || r.message.cost_center_project,
			};
		}
	} catch (e) {
		/* click dummy continues with mock defaults */
	}
}

async function onSaveSettings(payload) {
	settings.value = { ...payload };
	if (typeof frappe === "undefined") return;
	try {
		await frappe.call({
			method: "phamos.phamos.page.sales_action_panel.sales_action_panel.save_settings",
			args: { cost_center_project: payload.cost_center_project },
		});
		frappe.show_alert({ message: __("Settings saved"), indicator: "green" });
	} catch (e) {
		frappe.show_alert({
			message: __("Settings kept in session (click dummy)"),
			indicator: "orange",
		});
	}
}

onMounted(() => {
	loadSettings();
});

onUnmounted(() => {
	stopTick();
});
</script>

<template>
	<StartWorkModal
		v-if="showStartWork"
		:cost-center-project="settings.cost_center_project"
		:cost-center-project-name="settings.cost_center_project_name"
		@confirm="onStartWorkConfirm"
		@cancel="showStartWork = false"
	/>

	<div class="sap-root">
		<div class="sap-topbar">
			<button
				class="sap-menu-btn"
				:title="sidebarOpen ? 'Collapse' : 'Expand'"
				@click="sidebarOpen = !sidebarOpen"
			>
				<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
					<path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z" />
				</svg>
			</button>
			<span class="sap-topbar-title">Sales Action Panel</span>
			<span class="sap-topbar-badge">Click Dummy</span>
		</div>

		<div class="sap-split">
			<aside class="sap-sidebar" :class="{ 'sap-sidebar--hidden': !sidebarOpen }">
				<Sidebar
					:current-view="currentView"
					:counts="counts"
					:active-session="activeSession"
					:elapsed-seconds="elapsedSeconds"
					:cost-center-project-name="settings.cost_center_project_name"
					@change-view="changeView"
					@start-work="showStartWork = true"
					@open-settings="openSettings"
				/>
			</aside>

			<template v-if="currentView === 'settings'">
				<main class="sap-main sap-main--settings">
					<SettingsPanel
						:cost-center-project="settings.cost_center_project"
						@save="onSaveSettings"
					/>
				</main>
			</template>

			<template v-else>
				<section class="sap-list-col">
					<RecordList
						:view="currentView"
						:records="records"
						:selected-name="selectedName"
						@select="selectedName = $event"
					/>
				</section>
				<main class="sap-main">
					<RecordDetail
						:view="currentView"
						:record="selectedRecord"
						:related-contacts="relatedContacts"
						:related-addresses="relatedAddresses"
						:related-quotations="relatedQuotations"
						@open-related="openRelated"
					/>
				</main>
			</template>
		</div>
	</div>
</template>

<style>
.layout-main-section {
	padding: 0 !important;
	overflow: hidden;
}
</style>

<style scoped>
.sap-root {
	display: flex;
	flex-direction: column;
	width: 100%;
	min-height: calc(100vh - 108px);
	background: var(--bg-color);
	color: var(--text-color);
}
.sap-topbar {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 0 16px;
	height: 40px;
	border-bottom: 1px solid var(--border-color);
	background: var(--card-bg);
	flex-shrink: 0;
}
.sap-menu-btn {
	display: flex;
	align-items: center;
	justify-content: center;
	width: 28px;
	height: 28px;
	border: none;
	background: transparent;
	border-radius: 6px;
	color: var(--text-muted);
	cursor: pointer;
}
.sap-menu-btn:hover {
	background: var(--control-bg);
	color: var(--text-color);
}
.sap-topbar-title {
	font-size: 13px;
	font-weight: 600;
	color: var(--text-muted);
	letter-spacing: -0.01em;
}
.sap-topbar-badge {
	font-size: 10px;
	font-weight: 700;
	text-transform: uppercase;
	letter-spacing: 0.05em;
	padding: 2px 7px;
	border-radius: 999px;
	background: #ffedd5;
	color: #c2410c;
}
.sap-split {
	display: flex;
	flex: 1;
	overflow: hidden;
	min-height: 0;
}
.sap-sidebar {
	width: 240px;
	min-width: 240px;
	flex-shrink: 0;
	border-right: 1px solid var(--border-color);
	background: var(--card-bg);
	transition: width 0.22s cubic-bezier(0.4, 0, 0.2, 1),
		min-width 0.22s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.22s;
	overflow: hidden;
}
.sap-sidebar--hidden {
	width: 0;
	min-width: 0;
	opacity: 0;
	pointer-events: none;
}
.sap-list-col {
	width: 340px;
	min-width: 280px;
	max-width: 380px;
	flex-shrink: 0;
	border-right: 1px solid var(--border-color);
	overflow: hidden;
}
.sap-main {
	flex: 1;
	min-width: 0;
	overflow: hidden;
}
.sap-main--settings {
	width: 100%;
}
@media (max-width: 960px) {
	.sap-list-col {
		width: 280px;
		min-width: 240px;
	}
}
@media (max-width: 720px) {
	.sap-split {
		flex-direction: column;
	}
	.sap-sidebar {
		width: 100%;
		min-width: 0;
		max-height: 220px;
		border-right: none;
		border-bottom: 1px solid var(--border-color);
	}
	.sap-list-col {
		width: 100%;
		max-width: none;
		max-height: 40vh;
		border-right: none;
		border-bottom: 1px solid var(--border-color);
	}
}
</style>
