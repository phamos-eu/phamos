<script setup>
import { ref, onMounted } from "vue";
import { ACTIVITY_TYPES } from "../mockData";

const props = defineProps({
	costCenterProject: String,
	costCenterProjectName: String,
});

const emit = defineEmits(["confirm", "cancel"]);

const goal = ref("");
const activityType = ref(ACTIVITY_TYPES[0]);
const valueAdded = ref("100");
const hours = ref(1);
const startTime = ref(nowLocal());
const goalRef = ref(null);

onMounted(() => goalRef.value?.focus());

function nowLocal() {
	const d = new Date();
	const pad = (n) => String(n).padStart(2, "0");
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function submit() {
	if (!goal.value.trim()) {
		if (typeof frappe !== "undefined") {
			frappe.msgprint(__("Please enter a goal."));
		} else {
			alert("Please enter a goal.");
		}
		return;
	}
	if (!activityType.value) {
		if (typeof frappe !== "undefined") {
			frappe.msgprint(__("Please select an Activity Type."));
		} else {
			alert("Please select an Activity Type.");
		}
		return;
	}
	if (valueAdded.value === "" || valueAdded.value == null) {
		if (typeof frappe !== "undefined") {
			frappe.msgprint(__("Please select Value Added."));
		} else {
			alert("Please select Value Added.");
		}
		return;
	}
	emit("confirm", {
		goal: goal.value.trim(),
		activity_type: activityType.value,
		value_added: Number(valueAdded.value),
		expected_time: Math.round(parseFloat(hours.value || 1) * 3600),
		from_time: startTime.value.replace("T", " ") + ":00",
		project: props.costCenterProject,
		project_name: props.costCenterProjectName,
	});
}

function onKey(e) {
	if (e.key === "Escape") emit("cancel");
	if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
}
</script>

<template>
	<div class="mo-backdrop" @click.self="emit('cancel')" @keydown="onKey">
		<div class="mo" role="dialog" aria-modal="true" aria-labelledby="sap-start-title">
			<div class="mo__header">
				<div class="mo__header-icon">
					<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
						<path d="M8 5v14l11-7z" />
					</svg>
				</div>
				<div>
					<h2 id="sap-start-title" class="mo__title">Start Work</h2>
					<p class="mo__subtitle">
						Create a Timesheet record for sales work
					</p>
				</div>
				<button class="mo__close" @click="emit('cancel')" title="Close">
					<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
						<path
							d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"
						/>
					</svg>
				</button>
			</div>

			<div class="mo__body">
				<div class="mo__field">
					<label class="mo__label">
						Cost Center Project
					</label>
					<p class="mo__hint">
						Auto-selected from Sales Action Panel Settings.
					</p>
					<input
						class="mo__input mo__input--full"
						type="text"
						:value="costCenterProjectName || '— not configured —'"
						readonly
					/>
				</div>

				<div class="mo__field">
					<label class="mo__label">
						Goal
						<span class="mo__req">*</span>
					</label>
					<p class="mo__hint">
						What will you accomplish in this sales session?
					</p>
					<textarea
						ref="goalRef"
						v-model="goal"
						class="mo__textarea"
						rows="3"
						placeholder="e.g. Prepare Nordic Logistics pilot proposal and send follow-up"
					></textarea>
				</div>

				<div class="mo__row">
					<div class="mo__field">
						<label class="mo__label">
							Activity Type
							<span class="mo__req">*</span>
						</label>
						<p class="mo__hint">
							Categorize the sales activity (similar to Project Action Panel).
						</p>
						<select v-model="activityType" class="mo__input mo__input--full">
							<option v-for="t in ACTIVITY_TYPES" :key="t" :value="t">{{ t }}</option>
						</select>
					</div>

					<div class="mo__field">
						<label class="mo__label">
							Value Added
							<span class="mo__req">*</span>
						</label>
						<p class="mo__hint">in Percent (%)</p>
						<select v-model="valueAdded" class="mo__input mo__input--full">
							<option value="0">0</option>
							<option value="25">25</option>
							<option value="50">50</option>
							<option value="75">75</option>
							<option value="100">100</option>
						</select>
					</div>
				</div>

				<div class="mo__row">
					<div class="mo__field">
						<label class="mo__label">
							Expected duration
							<span class="mo__req">*</span>
						</label>
						<p class="mo__hint">How long do you expect this to take?</p>
						<div class="mo__duration-row">
							<input
								v-model.number="hours"
								type="number"
								class="mo__input"
								min="0.25"
								step="0.25"
							/>
							<span class="mo__unit">hours</span>
						</div>
					</div>

					<div class="mo__field">
						<label class="mo__label">From Time</label>
						<p class="mo__hint">Defaults to now. Adjust for retroactive logging.</p>
						<input v-model="startTime" type="datetime-local" class="mo__input mo__input--full" />
					</div>
				</div>
			</div>

			<div class="mo__footer">
				<span class="mo__kbd-hint">
					<kbd>Ctrl</kbd><kbd>↵</kbd> to start
				</span>
				<div class="mo__actions">
					<button class="mo__btn mo__btn--ghost" @click="emit('cancel')">Cancel</button>
					<button class="mo__btn mo__btn--primary" @click="submit">
						<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
							<path d="M8 5v14l11-7z" />
						</svg>
						Start Work
					</button>
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
.mo-backdrop {
	position: fixed;
	inset: 0;
	background: rgba(0, 0, 0, 0.4);
	backdrop-filter: blur(3px);
	display: flex;
	align-items: center;
	justify-content: center;
	z-index: 1100;
	padding: 20px;
}
.mo {
	background: var(--card-bg, #fff);
	border: 1px solid var(--border-color, #e5e7eb);
	border-radius: 12px;
	width: 560px;
	max-width: 100%;
	box-shadow: var(--shadow-md, 0 8px 24px rgba(0, 0, 0, 0.15));
	animation: mo-in 0.18s cubic-bezier(0.34, 1.56, 0.64, 1);
}
@keyframes mo-in {
	from {
		transform: scale(0.94);
		opacity: 0;
	}
}
.mo__header {
	display: flex;
	align-items: flex-start;
	gap: 12px;
	padding: 20px 20px 16px;
	border-bottom: 1px solid var(--border-color, #e5e7eb);
}
.mo__header-icon {
	width: 32px;
	height: 32px;
	background: var(--green-50, #f0fdf4);
	border-radius: 8px;
	display: flex;
	align-items: center;
	justify-content: center;
	color: var(--green-600, #16a34a);
	flex-shrink: 0;
}
.mo__title {
	margin: 0;
	font-size: 15px;
	font-weight: 700;
	color: var(--text-color, #111827);
	letter-spacing: -0.02em;
}
.mo__subtitle {
	margin: 3px 0 0;
	font-size: 12px;
	color: var(--text-muted, #6b7280);
}
.mo__close {
	margin-left: auto;
	background: none;
	border: none;
	color: var(--text-muted, #6b7280);
	cursor: pointer;
	padding: 4px;
	border-radius: 4px;
	display: flex;
}
.mo__close:hover {
	background: var(--control-bg, #f3f4f6);
	color: var(--text-color, #111827);
}
.mo__body {
	padding: 18px 20px;
	display: flex;
	flex-direction: column;
	gap: 16px;
}
.mo__row {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 14px;
}
.mo__field {
	display: flex;
	flex-direction: column;
	gap: 4px;
}
.mo__label {
	font-size: 13px;
	font-weight: 600;
	color: var(--text-color, #111827);
}
.mo__req {
	color: var(--red-500, #ef4444);
	margin-left: 2px;
}
.mo__hint {
	font-size: 12px;
	color: var(--text-muted, #6b7280);
	margin: 0;
}
.mo__textarea,
.mo__input {
	padding: 9px 12px;
	border: 1px solid var(--border-color, #e5e7eb);
	border-radius: 7px;
	background: var(--card-bg, #fff);
	color: var(--text-color, #111827);
	font-size: 13.5px;
	font-family: inherit;
	resize: vertical;
	box-sizing: border-box;
}
.mo__input--full,
.mo__textarea {
	width: 100%;
}
.mo__textarea:focus,
.mo__input:focus {
	outline: none;
	border-color: var(--primary, #2563eb);
	box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}
.mo__input[readonly] {
	background: var(--control-bg, #f3f4f6);
	color: var(--text-muted, #6b7280);
}
.mo__duration-row {
	display: flex;
	align-items: center;
	gap: 8px;
}
.mo__input {
	width: 100px;
}
.mo__unit {
	font-size: 13px;
	color: var(--text-muted, #6b7280);
	font-weight: 500;
}
.mo__footer {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 14px 20px;
	border-top: 1px solid var(--border-color, #e5e7eb);
	background: var(--bg-color, #f9fafb);
	border-radius: 0 0 12px 12px;
}
.mo__kbd-hint {
	display: flex;
	align-items: center;
	gap: 3px;
}
kbd {
	font-size: 10px;
	font-family: inherit;
	background: var(--control-bg, #f3f4f6);
	border: 1px solid var(--border-color, #e5e7eb);
	border-radius: 3px;
	padding: 1px 5px;
	color: var(--text-muted, #6b7280);
}
.mo__actions {
	display: flex;
	gap: 8px;
	align-items: center;
}
.mo__btn {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	padding: 7px 14px;
	border-radius: 7px;
	font-size: 13px;
	font-weight: 600;
	cursor: pointer;
	border: 1px solid transparent;
	line-height: 1;
}
.mo__btn--ghost {
	background: none;
	border-color: var(--border-color, #e5e7eb);
	color: var(--text-muted, #6b7280);
}
.mo__btn--ghost:hover {
	background: var(--control-bg, #f3f4f6);
	color: var(--text-color, #111827);
}
.mo__btn--primary {
	background: var(--green-600, #16a34a);
	color: #fff;
	border-color: var(--green-600, #16a34a);
}
.mo__btn--primary:hover {
	background: var(--green-700, #15803d);
}
@media (max-width: 640px) {
	.mo__row {
		grid-template-columns: 1fr;
	}
}
</style>
