<script setup>
import { ref, onMounted } from "vue";
import { call } from "frappe-ui";
import {
	formatForApi,
	parseDatetimeLocalValue,
	toDatetimeLocalValue,
} from "@iown/utils/datetime";

const props = defineProps({
  projectName: { type: String, default: "" },
  project: { type: String, default: "" },
});
const emit = defineEmits(["confirm", "cancel"]);

const SETTINGS_API = "phamos.api.hr_spa";

const goal = ref("");
const hours = ref(1);
const task = ref("");
const tasks = ref([]);
const goalRef = ref(null);
const startTime = ref(toDatetimeLocalValue(new Date()));
const error = ref("");

onMounted(async () => {
  goalRef.value?.focus();
  if (props.project) {
    try {
      tasks.value = await call(`${SETTINGS_API}.get_timesheet_project_tasks`, {
        project: props.project,
      });
    } catch {
      tasks.value = [];
    }
  }
});

function submit() {
  error.value = "";
  if (!goal.value.trim()) { error.value = "Please enter a goal."; return; }
  if (!hours.value || hours.value < 0.25) { error.value = "Minimum expected time is 15 minutes (0.25h)."; return; }
  const payload = { goal: goal.value.trim(), expectedTime: Math.round(parseFloat(hours.value) * 3600) };
  const startDate = parseDatetimeLocalValue(startTime.value);
  if (startDate) {
    const apiTime = formatForApi(startDate);
    if (apiTime) payload.manualStartTime = apiTime;
  }
  if (task.value) payload.task = task.value;
  emit("confirm", payload);
}

function onKey(e) {
  if (e.key === "Escape") emit("cancel");
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
}
</script>

<template>
  <div class="mo-backdrop" @click.self="emit('cancel')" @keydown="onKey">
    <div class="mo" role="dialog" aria-modal="true">
      <div class="mo__header">
        <div class="mo__header-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5v14l11-7z"/>
          </svg>
        </div>
        <div>
          <h2 class="mo__title">Start Session</h2>
          <p class="mo__subtitle">{{ projectName || "HR timesheet project" }}</p>
        </div>
        <button class="mo__close" @click="emit('cancel')" title="Close">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
          </svg>
        </button>
      </div>

      <div class="mo__body">
        <div class="mo__field">
          <label class="mo__label">
            Goal
            <span class="mo__req">*</span>
          </label>
          <p class="mo__hint">What will you accomplish in this session?</p>
          <textarea
            ref="goalRef"
            v-model="goal"
            class="mo__textarea"
            rows="3"
            placeholder="e.g. Fix the API pagination bug and write tests"
          ></textarea>
        </div>

        <div v-if="tasks.length" class="mo__field">
          <label class="mo__label">Task</label>
          <p class="mo__hint">Optional — link this session to a project task.</p>
          <select v-model="task" class="mo__select">
            <option value="">— None —</option>
            <option v-for="t in tasks" :key="t.name" :value="t.name">
              {{ t.subject || t.name }}
            </option>
          </select>
        </div>

        <div class="mo__field">
          <label class="mo__label">
            Expected duration
            <span class="mo__req">*</span>
          </label>
          <p class="mo__hint">How long do you expect this to take?</p>
          <div class="mo__duration-row">
            <input v-model.number="hours" type="number" class="mo__input" min="0.25" step="0.25" />
            <span class="mo__unit">hours</span>
            <span class="mo__duration-hint">
              {{ hours ? `= ${Math.floor(hours)}h ${Math.round((hours % 1) * 60)}m` : "" }}
            </span>
          </div>
        </div>

        <div class="mo__field">
          <label class="mo__label">Start time</label>
          <p class="mo__hint">Set a past time to log retroactively, or leave as-is to start now.</p>
          <input v-model="startTime" type="datetime-local" class="mo__input mo__input--datetime" />
        </div>
        <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
      </div>

      <div class="mo__footer">
        <span class="mo__kbd-hint">
          <kbd>Ctrl</kbd><kbd>↵</kbd> to start
        </span>
        <div class="mo__actions">
          <button class="mo__btn mo__btn--ghost" @click="emit('cancel')">Cancel</button>
          <button class="mo__btn mo__btn--primary" @click="submit">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
            Start Session
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mo-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.4);
  backdrop-filter: blur(3px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1100;
  padding: 20px;
}
.mo {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  width: 460px;
  max-width: 100%;
  box-shadow: var(--shadow-md, 0 8px 24px rgba(0,0,0,0.15));
  animation: mo-in 0.18s cubic-bezier(0.34,1.56,0.64,1);
}
@keyframes mo-in { from { transform: scale(0.94); opacity: 0; } }

.mo__header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 20px 20px 16px;
  border-bottom: 1px solid var(--border-color);
}
.mo__header-icon {
  width: 32px; height: 32px;
  background: var(--blue-50, #eff6ff);
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  color: var(--primary);
  flex-shrink: 0;
  margin-top: 1px;
}
.mo__title { margin: 0; font-size: 15px; font-weight: 700; color: var(--text-color); letter-spacing: -0.02em; }
.mo__subtitle {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 340px;
}
.mo__close {
  margin-left: auto;
  background: none; border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.12s, color 0.12s;
}
.mo__close:hover { background: var(--control-bg); color: var(--text-color); }

.mo__body { padding: 18px 20px; display: flex; flex-direction: column; gap: 16px; }
.mo__field { display: flex; flex-direction: column; gap: 4px; }
.mo__label { font-size: 13px; font-weight: 600; color: var(--text-color); }
.mo__req { color: var(--red-500, #ef4444); margin-left: 2px; }
.mo__hint { font-size: 12px; color: var(--text-muted); margin: 0; }
.mo__textarea, .mo__input, .mo__select {
  width: 100%;
  padding: 9px 12px;
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: var(--card-bg);
  color: var(--text-color);
  font-size: 13.5px;
  font-family: inherit;
  resize: vertical;
  transition: border-color 0.15s, box-shadow 0.15s;
  box-sizing: border-box;
}
.mo__textarea:focus, .mo__input:focus, .mo__select:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37,99,235,0.1);
}
.mo__duration-row { display: flex; align-items: center; gap: 8px; }
.mo__input { width: 100px; flex-shrink: 0; }
.mo__input--datetime { width: 100%; }
.mo__unit { font-size: 13px; color: var(--text-muted); font-weight: 500; }
.mo__duration-hint { font-size: 12px; color: var(--text-muted); margin-left: 4px; }

.mo__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-top: 1px solid var(--border-color);
  background: var(--bg-color);
  border-radius: 0 0 12px 12px;
}
.mo__kbd-hint { display: flex; align-items: center; gap: 3px; }
kbd {
  font-size: 10px; font-family: inherit;
  background: var(--control-bg);
  border: 1px solid var(--border-color);
  border-radius: 3px;
  padding: 1px 5px;
  color: var(--text-muted);
}
.mo__actions { display: flex; gap: 8px; align-items: center; }
.mo__btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 13px; font-weight: 600;
  cursor: pointer; border: 1px solid transparent;
  transition: background 0.12s, border-color 0.12s;
  line-height: 1;
}
.mo__btn--ghost { background: none; border-color: var(--border-color); color: var(--text-muted); }
.mo__btn--ghost:hover { background: var(--control-bg); color: var(--text-color); }
.mo__btn--primary { background: var(--primary); color: #fff; border-color: var(--primary); }
.mo__btn--primary:hover { background: var(--blue-700, #1d4ed8); }
</style>
