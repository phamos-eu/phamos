<script setup>
import { computed } from "vue";
import { VIEWS } from "../mockData";

const props = defineProps({
	currentView: String,
	counts: Object,
	activeSession: Object,
	elapsedSeconds: Number,
	costCenterProjectName: String,
});

const emit = defineEmits(["change-view", "start-work", "open-settings"]);

const userName =
	typeof frappe !== "undefined" && frappe.user?.full_name
		? frappe.user.full_name()
		: "Sales User";
const userInitial = (userName[0] || "S").toUpperCase();

const isRunning = computed(() => !!props.activeSession);

function fmtElapsed(s) {
	if (!s) return "00:00:00";
	const h = Math.floor(s / 3600);
	const m = Math.floor((s % 3600) / 60);
	const sec = s % 60;
	return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

const ICONS = {
	lead: "M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z",
	opportunity:
		"M13 7h8m0 0v8m0-8l-8 8-4-4-6 6",
	customer:
		"M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4",
	quotation:
		"M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
	contact:
		"M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z",
	address:
		"M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z M15 11a3 3 0 11-6 0 3 3 0 016 0z",
};
</script>

<template>
	<div class="sap-sb">
		<div class="sap-sb__user">
			<div class="sap-sb__avatar">{{ userInitial }}</div>
			<div class="sap-sb__user-info">
				<div class="sap-sb__user-name">{{ userName }}</div>
				<div class="sap-sb__user-role">Sales</div>
			</div>
		</div>

		<div class="sap-sb__start-wrap">
			<button
				class="sap-sb__start-btn"
				:class="{ 'sap-sb__start-btn--running': isRunning }"
				:disabled="isRunning"
				@click="emit('start-work')"
			>
				<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
					<path d="M8 5v14l11-7z" />
				</svg>
				{{ isRunning ? "Work in progress" : "Start Work" }}
			</button>
			<p v-if="costCenterProjectName" class="sap-sb__project-hint" :title="costCenterProjectName">
				Project: {{ costCenterProjectName }}
			</p>
		</div>

		<div
			v-if="activeSession"
			class="sap-sb__session"
		>
			<div class="sap-sb__session-head">
				<span class="sap-sb__dot"></span>
				<span class="sap-sb__session-state">Running</span>
				<span class="sap-sb__session-timer">{{ fmtElapsed(elapsedSeconds) }}</span>
			</div>
			<div class="sap-sb__session-goal">{{ activeSession.goal }}</div>
			<div class="sap-sb__session-meta">
				{{ activeSession.activity_type }} · {{ activeSession.value_added }}% value added
			</div>
		</div>

		<div class="sap-sb__section-label">CRM</div>
		<nav class="sap-sb__nav">
			<button
				v-for="view in VIEWS"
				:key="view.key"
				class="sap-sb__nav-item"
				:class="{ 'sap-sb__nav-item--active': currentView === view.key }"
				@click="emit('change-view', view.key)"
			>
				<svg
					class="sap-sb__nav-svg"
					width="14"
					height="14"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="1.8"
					stroke-linecap="round"
					stroke-linejoin="round"
				>
					<path :d="ICONS[view.icon]" />
				</svg>
				<span class="sap-sb__nav-label">{{ view.label }}</span>
				<span class="sap-sb__nav-count">{{ counts[view.key] || 0 }}</span>
			</button>
		</nav>

		<div class="sap-sb__spacer"></div>

		<div class="sap-sb__section-label">Configuration</div>
		<nav class="sap-sb__nav">
			<button
				class="sap-sb__nav-item"
				:class="{ 'sap-sb__nav-item--active': currentView === 'settings' }"
				@click="emit('open-settings')"
			>
				<svg
					class="sap-sb__nav-svg"
					width="14"
					height="14"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="1.8"
					stroke-linecap="round"
					stroke-linejoin="round"
				>
					<path
						d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
					/>
					<path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
				</svg>
				<span class="sap-sb__nav-label">Sales Action Panel Settings</span>
			</button>
		</nav>
	</div>
</template>

<style scoped>
.sap-sb {
	display: flex;
	flex-direction: column;
	height: 100%;
	font-size: 13px;
	overflow-y: auto;
}
.sap-sb__user {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 14px 14px 12px;
	border-bottom: 1px solid var(--border-color);
	flex-shrink: 0;
}
.sap-sb__avatar {
	width: 32px;
	height: 32px;
	border-radius: 50%;
	background: var(--primary);
	color: #fff;
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: 13px;
	font-weight: 700;
	flex-shrink: 0;
}
.sap-sb__user-name {
	font-size: 13px;
	font-weight: 600;
	color: var(--text-color);
	line-height: 1.2;
}
.sap-sb__user-role {
	font-size: 11px;
	color: var(--text-muted);
}
.sap-sb__start-wrap {
	padding: 12px 10px 4px;
	flex-shrink: 0;
}
.sap-sb__start-btn {
	display: flex;
	align-items: center;
	justify-content: center;
	gap: 8px;
	width: 100%;
	padding: 10px 12px;
	border: none;
	border-radius: 8px;
	background: var(--green-600, #16a34a);
	color: #fff;
	font-size: 13px;
	font-weight: 700;
	cursor: pointer;
	transition: background 0.12s, transform 0.12s;
}
.sap-sb__start-btn:hover:not(:disabled) {
	background: var(--green-700, #15803d);
	transform: translateY(-1px);
}
.sap-sb__start-btn:disabled,
.sap-sb__start-btn--running {
	opacity: 0.7;
	cursor: not-allowed;
	transform: none;
	background: var(--gray-500, #6b7280);
}
.sap-sb__project-hint {
	margin: 6px 2px 0;
	font-size: 11px;
	color: var(--text-muted);
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
}
.sap-sb__session {
	margin: 10px 10px 0;
	padding: 10px 12px;
	border-radius: 8px;
	background: var(--green-50, #f0fdf4);
	border: 1px solid var(--green-200, #bbf7d0);
	flex-shrink: 0;
}
.sap-sb__session-head {
	display: flex;
	align-items: center;
	gap: 6px;
	margin-bottom: 4px;
}
.sap-sb__dot {
	width: 7px;
	height: 7px;
	border-radius: 50%;
	background: var(--green-500, #22c55e);
	animation: sap-pulse 2s ease-in-out infinite;
}
@keyframes sap-pulse {
	0%,
	100% {
		box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.25);
	}
	50% {
		box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.1);
	}
}
.sap-sb__session-state {
	font-size: 10.5px;
	font-weight: 700;
	text-transform: uppercase;
	letter-spacing: 0.06em;
	color: var(--text-muted);
	flex: 1;
}
.sap-sb__session-timer {
	font-family: var(--font-monospace, monospace);
	font-size: 12.5px;
	font-weight: 700;
	color: var(--text-color);
}
.sap-sb__session-goal {
	font-size: 11.5px;
	color: var(--text-muted);
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
}
.sap-sb__session-meta {
	margin-top: 3px;
	font-size: 10.5px;
	color: var(--text-muted);
}
.sap-sb__section-label {
	padding: 14px 14px 4px;
	font-size: 10px;
	font-weight: 700;
	text-transform: uppercase;
	letter-spacing: 0.08em;
	color: var(--text-muted);
	flex-shrink: 0;
}
.sap-sb__nav {
	padding: 2px 6px;
	flex-shrink: 0;
}
.sap-sb__nav-item {
	display: flex;
	align-items: center;
	gap: 8px;
	width: 100%;
	padding: 7px 8px;
	border: none;
	background: transparent;
	border-radius: 6px;
	cursor: pointer;
	color: var(--text-muted);
	transition: background 0.1s, color 0.1s;
	text-align: left;
	margin-bottom: 1px;
	font-size: 13px;
}
.sap-sb__nav-item:hover {
	background: var(--control-bg);
	color: var(--text-color);
}
.sap-sb__nav-item--active {
	background: var(--blue-50, #eff6ff);
	color: var(--primary);
	font-weight: 600;
}
.sap-sb__nav-svg {
	flex-shrink: 0;
}
.sap-sb__nav-label {
	flex: 1;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}
.sap-sb__nav-count {
	font-size: 11px;
	font-weight: 600;
	background: var(--control-bg);
	color: var(--text-muted);
	border-radius: 10px;
	padding: 1px 6px;
	flex-shrink: 0;
}
.sap-sb__nav-item--active .sap-sb__nav-count {
	background: var(--primary);
	color: #fff;
}
.sap-sb__spacer {
	flex: 1;
	min-height: 12px;
}
</style>
