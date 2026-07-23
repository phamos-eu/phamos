<script setup>
import { ref, watch } from "vue";
import { SAMPLE_PROJECTS } from "../mockData";

const props = defineProps({
	costCenterProject: String,
});

const emit = defineEmits(["save"]);

const selected = ref(props.costCenterProject || SAMPLE_PROJECTS[0].name);
const savedFlash = ref(false);

watch(
	() => props.costCenterProject,
	(v) => {
		if (v) selected.value = v;
	}
);

function save() {
	const project = SAMPLE_PROJECTS.find((p) => p.name === selected.value);
	emit("save", {
		cost_center_project: selected.value,
		cost_center_project_name: project?.project_name || selected.value,
	});
	savedFlash.value = true;
	setTimeout(() => {
		savedFlash.value = false;
	}, 1800);
}
</script>

<template>
	<div class="sap-settings">
		<header class="sap-settings__header">
			<div class="sap-settings__eyebrow">Configuration</div>
			<h2 class="sap-settings__title">Sales Action Panel Settings</h2>
			<p class="sap-settings__intro">
				Defaults applied when sales users start a Timesheet from the
				<strong>Start Work</strong> button.
			</p>
		</header>

		<section class="sap-settings__card">
			<h3 class="sap-settings__section-title">Timesheet Defaults</h3>

			<div class="sap-settings__field">
				<label class="sap-settings__label">Cost Center Project</label>
				<p class="sap-settings__hint">
					Project auto-selected when starting the Timesheet via Start Work.
				</p>
				<select v-model="selected" class="sap-settings__select">
					<option v-for="p in SAMPLE_PROJECTS" :key="p.name" :value="p.name">
						{{ p.project_name }} ({{ p.name }})
					</option>
				</select>
			</div>

			<div class="sap-settings__actions">
				<button class="sap-settings__save" @click="save">Save Settings</button>
				<span v-if="savedFlash" class="sap-settings__flash">Saved</span>
			</div>
		</section>

		<section class="sap-settings__note">
			This is the click-dummy settings surface. In production this maps to the
			<strong>Sales Action Panel Settings</strong> Single doctype.
		</section>
	</div>
</template>

<style scoped>
.sap-settings {
	height: 100%;
	overflow-y: auto;
	background: var(--bg-color);
	padding: 22px;
}
.sap-settings__header {
	margin-bottom: 18px;
}
.sap-settings__eyebrow {
	font-size: 10.5px;
	font-weight: 700;
	text-transform: uppercase;
	letter-spacing: 0.08em;
	color: var(--text-muted);
	margin-bottom: 4px;
}
.sap-settings__title {
	margin: 0;
	font-size: 20px;
	font-weight: 700;
	letter-spacing: -0.03em;
	color: var(--text-color);
}
.sap-settings__intro {
	margin: 8px 0 0;
	font-size: 13px;
	color: var(--text-muted);
	max-width: 520px;
	line-height: 1.45;
}
.sap-settings__card {
	background: var(--card-bg);
	border: 1px solid var(--border-color);
	border-radius: 10px;
	padding: 18px 20px;
	max-width: 560px;
}
.sap-settings__section-title {
	margin: 0 0 14px;
	font-size: 11px;
	font-weight: 700;
	text-transform: uppercase;
	letter-spacing: 0.08em;
	color: var(--text-muted);
}
.sap-settings__field {
	display: flex;
	flex-direction: column;
	gap: 4px;
}
.sap-settings__label {
	font-size: 13px;
	font-weight: 600;
	color: var(--text-color);
}
.sap-settings__hint {
	margin: 0;
	font-size: 12px;
	color: var(--text-muted);
}
.sap-settings__select {
	margin-top: 6px;
	padding: 9px 12px;
	border: 1px solid var(--border-color);
	border-radius: 7px;
	background: var(--card-bg);
	color: var(--text-color);
	font-size: 13.5px;
	font-family: inherit;
}
.sap-settings__actions {
	display: flex;
	align-items: center;
	gap: 12px;
	margin-top: 18px;
}
.sap-settings__save {
	padding: 8px 14px;
	border: none;
	border-radius: 7px;
	background: var(--primary);
	color: #fff;
	font-size: 13px;
	font-weight: 600;
	cursor: pointer;
}
.sap-settings__save:hover {
	filter: brightness(0.95);
}
.sap-settings__flash {
	font-size: 12px;
	font-weight: 600;
	color: var(--green-600, #16a34a);
}
.sap-settings__note {
	margin-top: 16px;
	font-size: 12px;
	color: var(--text-muted);
	max-width: 560px;
	line-height: 1.45;
}
</style>
