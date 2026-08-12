<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";

const props = defineProps({
  project: Object,   // { name, project_name, customer_name }
  startFrom: String, // system-tz "YYYY-MM-DD HH:mm:ss"
});
const emit = defineEmits(["confirm", "close"]);

const goal = ref("");
const result = ref("");
const activityType = ref("");
const percentBillable = ref(0);
const goalRef = ref(null);
const liveNow = ref(new Date());
let liveInterval = null;

const ACTIVITY_TYPES = ["Working Alone", "Working with Customer", "Working With Team"];
const billableOptions = [
  { value: 100, label: "100%" },
  { value: 75,  label: "75%"  },
  { value: 50,  label: "50%"  },
  { value: 25,  label: "25%"  },
  { value: 0,   label: "0%"   },
];

onMounted(() => {
  goalRef.value?.focus();
  liveInterval = setInterval(() => { liveNow.value = new Date(); }, 1000);
});
onUnmounted(() => clearInterval(liveInterval));

const meetingDuration = computed(() => {
  liveNow.value; // trigger every second
  if (!props.startFrom) return "—";
  const sysTz = frappe.boot?.time_zone?.system;
  let secs = 0;
  if (sysTz && typeof moment !== "undefined" && moment.tz) {
    try { secs = Math.max(0, moment().diff(moment.tz(props.startFrom, sysTz), "seconds")); } catch(e) {}
  } else {
    const from = new Date(props.startFrom.replace(" ", "T"));
    secs = Math.max(0, Math.round((Date.now() - from) / 1000));
  }
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
});

function fmtTime(str) {
  if (!str) return "—";
  const sysTz = frappe.boot?.time_zone?.system;
  const uTz   = frappe.boot?.time_zone?.user;
  if (sysTz && uTz && typeof moment !== "undefined" && moment.tz) {
    try { return moment.tz(str, sysTz).tz(uTz).format("HH:mm"); } catch(e) {}
  }
  return str.substring(11, 16);
}

function submit() {
  if (!activityType.value)   { frappe.msgprint(__("Please select an Activity Type.")); return; }
  if (!goal.value.trim())    { frappe.msgprint(__("Please enter a goal.")); return; }
  if (!result.value.trim())  { frappe.msgprint(__("Please describe what was done in the meeting.")); return; }
  emit("confirm", {
    activityType: activityType.value,
    goal: goal.value.trim(),
    result: result.value.trim(),
    percentBillable: percentBillable.value,
  });
}

function onKey(e) {
  if (e.key === "Escape") emit("close");
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
}
</script>

<template>
  <div class="mo-backdrop" @click.self="emit('close')" @keydown="onKey">
    <div class="mo" role="dialog" aria-modal="true">
      <!-- Header -->
      <div class="mo__header">
        <div class="mo__header-icon mo__header-icon--purple">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/>
          </svg>
        </div>
        <div class="mo__header-text">
          <h2 class="mo__title">Log HR / Meeting Time</h2>
          <p class="mo__subtitle">
            Project: <strong>{{ project?.project_name || project?.name }}</strong>
            <span class="mo__dur"> · started {{ fmtTime(startFrom) }} · {{ meetingDuration }}</span>
          </p>
        </div>
        <button class="mo__close" @click="emit('close')" title="Close">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
          </svg>
        </button>
      </div>

      <!-- Body -->
      <div class="mo__body">
        <div class="mo__row">
          <div class="mo__field mo__field--half">
            <label class="mo__label">Activity Type <span class="mo__req">*</span></label>
            <p class="mo__hint">Type of activity</p>
            <select v-model="activityType" class="mo__select">
              <option value="">— Select type —</option>
              <option v-for="t in ACTIVITY_TYPES" :key="t" :value="t">{{ t }}</option>
            </select>
          </div>

          <div class="mo__field mo__field--half">
            <label class="mo__label">Billable %</label>
            <p class="mo__hint">How much is billable?</p>
            <div class="mo__billable-row">
              <button
                v-for="opt in billableOptions"
                :key="opt.value"
                type="button"
                class="mo__bill-opt"
                :class="{ 'mo__bill-opt--active': percentBillable === opt.value }"
                @click="percentBillable = opt.value"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
        </div>

        <div class="mo__field">
          <label class="mo__label">Goal <span class="mo__req">*</span></label>
          <p class="mo__hint">What was the meeting or activity about?</p>
          <textarea
            ref="goalRef"
            v-model="goal"
            class="mo__textarea"
            rows="2"
            placeholder="e.g. Weekly team sync, 1:1, HR onboarding"
          ></textarea>
        </div>

        <div class="mo__field">
          <label class="mo__label">Result <span class="mo__req">*</span></label>
          <p class="mo__hint">What was the outcome?</p>
          <textarea
            v-model="result"
            class="mo__textarea"
            rows="2"
            placeholder="e.g. Discussed roadmap, clarified leave policy"
          ></textarea>
        </div>
      </div>

      <!-- Footer -->
      <div class="mo__footer">
        <span class="mo__kbd-hint"><kbd>Ctrl</kbd><kbd>↵</kbd> to submit</span>
        <div class="mo__actions">
          <button class="mo__btn mo__btn--ghost" @click="emit('close')">Cancel</button>
          <button class="mo__btn mo__btn--purple" @click="submit">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
            Stop Meeting
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
  display: flex; align-items: center; justify-content: center;
  z-index: 1100; padding: 20px;
}
.mo {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  width: 640px; max-width: 100%;
  box-shadow: var(--shadow-md, 0 8px 24px rgba(0,0,0,0.15));
  animation: mo-in 0.18s cubic-bezier(0.34,1.56,0.64,1);
}
@keyframes mo-in { from { transform: scale(0.94); opacity: 0; } }

.mo__header {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--border-color);
}
.mo__header-icon {
  width: 32px; height: 32px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; margin-top: 1px;
}
.mo__header-icon--purple { background: #f3e8ff; color: #7c3aed; }
.mo__header-text { flex: 1; min-width: 0; }
.mo__title { margin: 0; font-size: 15px; font-weight: 700; color: var(--text-color); letter-spacing: -0.02em; }
.mo__subtitle { margin: 3px 0 0; font-size: 12px; color: var(--text-muted); }
.mo__dur { color: var(--text-color); font-weight: 700; font-variant-numeric: tabular-nums; }
.mo__close {
  margin-left: auto; background: none; border: none; color: var(--text-muted);
  cursor: pointer; padding: 4px; border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.12s, color 0.12s; flex-shrink: 0;
}
.mo__close:hover { background: var(--control-bg); color: var(--text-color); }

.mo__body { padding: 16px 20px; display: flex; flex-direction: column; gap: 14px; }
.mo__row { display: flex; gap: 14px; align-items: flex-start; }
.mo__field { display: flex; flex-direction: column; gap: 4px; }
.mo__field--half { flex: 1; min-width: 0; }
.mo__label { font-size: 13px; font-weight: 600; color: var(--text-color); }
.mo__req { color: var(--red-500, #ef4444); margin-left: 2px; }
.mo__hint { font-size: 12px; color: var(--text-muted); margin: 0; }

.mo__select, .mo__textarea {
  width: 100%; padding: 8px 12px;
  border: 1px solid var(--border-color); border-radius: 7px;
  background: var(--card-bg); color: var(--text-color);
  font-size: 13.5px; font-family: inherit;
  box-sizing: border-box;
}
.mo__textarea { resize: vertical; }
.mo__select:focus, .mo__textarea:focus {
  outline: none; border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37,99,235,0.1);
}

.mo__billable-row {
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px;
}
.mo__bill-opt {
  padding: 8px 4px; border: 1px solid var(--border-color); border-radius: 7px;
  background: var(--card-bg); color: var(--text-color); cursor: pointer;
  font-size: 13px; font-weight: 600; transition: background 0.12s, border-color 0.12s;
}
.mo__bill-opt:hover { background: var(--control-bg); }
.mo__bill-opt--active { background: #f3e8ff; border-color: #7c3aed; color: #7c3aed; }

.mo__footer {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px;
  border-top: 1px solid var(--border-color);
  background: var(--bg-color);
  border-radius: 0 0 12px 12px;
}
.mo__kbd-hint { display: flex; align-items: center; gap: 3px; }
kbd {
  font-size: 10px; font-family: inherit;
  background: var(--control-bg); border: 1px solid var(--border-color);
  border-radius: 3px; padding: 1px 5px; color: var(--text-muted);
}
.mo__actions { display: flex; gap: 8px; align-items: center; }
.mo__btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 14px; border-radius: 7px;
  font-size: 13px; font-weight: 600; cursor: pointer;
  border: 1px solid transparent; line-height: 1;
  transition: background 0.12s, border-color 0.12s;
}
.mo__btn--ghost { background: none; border-color: var(--border-color); color: var(--text-muted); }
.mo__btn--ghost:hover { background: var(--control-bg); color: var(--text-color); }
.mo__btn--purple { background: #7c3aed; color: #fff; border-color: #7c3aed; }
.mo__btn--purple:hover { background: #6d28d9; }
</style>
