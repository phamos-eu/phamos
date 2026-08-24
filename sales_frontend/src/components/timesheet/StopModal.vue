<script setup>
import { ref, onMounted } from "vue";
import { call } from "frappe-ui";
import {
	formatForApi,
	parseDatetimeLocalValue,
	toDatetimeLocalValue,
} from "@iown/utils/datetime";

const emit = defineEmits(["confirm", "cancel"]);

const result = ref("");
const percentBillable = ref(100);
const activityType = ref("");
const resultRef = ref(null);
const endTime = ref(toDatetimeLocalValue(new Date()));
const error = ref("");
const activityTypes = ref([]);

onMounted(async () => {
  resultRef.value?.focus();
  try {
    const rows = await call("frappe.client.get_list", {
      doctype: "Activity Type",
      fields: ["name"],
      limit: 100,
      order_by: "name asc",
    });
    activityTypes.value = (rows || []).map((r) => r.name);
  } catch {
    activityTypes.value = [];
  }
});

function submit() {
  error.value = "";
  if (!result.value.trim()) { error.value = "Please describe what you accomplished."; return; }
  if (!activityType.value) { error.value = "Please select an activity type."; return; }
  const payload = {
    result: result.value.trim(),
    percentBillable: percentBillable.value,
    activityType: activityType.value,
  };
  const endDate = parseDatetimeLocalValue(endTime.value);
  if (endDate) {
    const apiTime = formatForApi(endDate);
    if (apiTime) payload.manualEndTime = apiTime;
  }
  emit("confirm", payload);
}

function onKey(e) {
  if (e.key === "Escape") emit("cancel");
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
}

const billableOptions = [
  { value: 100, label: "100%", hint: "Fully billable" },
  { value: 75,  label: "75%",  hint: "" },
  { value: 50,  label: "50%",  hint: "Partially billable" },
  { value: 25,  label: "25%",  hint: "" },
  { value: 0,   label: "0%",   hint: "Internal / non-billable" },
];
</script>

<template>
  <div class="mo-backdrop" @click.self="emit('cancel')" @keydown="onKey">
    <div class="mo" role="dialog" aria-modal="true">
      <!-- Header -->
      <div class="mo__header">
        <div class="mo__header-icon mo__header-icon--red">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M6 6h12v12H6z"/>
          </svg>
        </div>
        <div>
          <h2 class="mo__title">Stop &amp; Submit Session</h2>
          <p class="mo__subtitle">Describe your outcome and confirm billable percentage</p>
        </div>
        <button class="mo__close" @click="emit('cancel')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
          </svg>
        </button>
      </div>

      <!-- Body -->
      <div class="mo__body">
        <div class="mo__field">
          <label class="mo__label">Result <span class="mo__req">*</span></label>
          <p class="mo__hint">What did you accomplish in this session?</p>
          <textarea
            ref="resultRef"
            v-model="result"
            class="mo__textarea"
            rows="3"
            placeholder="e.g. Fixed the pagination bug, added 4 unit tests, opened MR !38"
          ></textarea>
        </div>

        <div class="mo__field">
          <label class="mo__label">Activity type <span class="mo__req">*</span></label>
          <p class="mo__hint">How were you working during this session?</p>
          <select v-model="activityType" class="mo__select">
            <option value="">— Select —</option>
            <option v-for="at in activityTypes" :key="at" :value="at">{{ at }}</option>
          </select>
        </div>

        <div class="mo__field">
          <label class="mo__label">End time</label>
          <p class="mo__hint">Set a past time to log retroactively, or leave as-is to stop now.</p>
          <input v-model="endTime" type="datetime-local" class="mo__input--datetime" />
        </div>

        <div class="mo__field">
          <label class="mo__label">Billable percentage</label>
          <p class="mo__hint">How much of this time is billable to the client?</p>
          <div class="mo__billable-grid">
            <button
              v-for="opt in billableOptions"
              :key="opt.value"
              type="button"
              class="mo__bill-opt"
              :class="{ 'mo__bill-opt--active': percentBillable === opt.value }"
              @click="percentBillable = opt.value"
            >
              <span class="mo__bill-pct">{{ opt.label }}</span>
              <span v-if="opt.hint" class="mo__bill-hint">{{ opt.hint }}</span>
            </button>
          </div>
        </div>
        <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
      </div>

      <!-- Footer -->
      <div class="mo__footer">
        <span class="mo__kbd-hint">
          <kbd>Ctrl</kbd><kbd>↵</kbd> to submit
        </span>
        <div class="mo__actions">
          <button class="mo__btn mo__btn--ghost" @click="emit('cancel')">Cancel</button>
          <button class="mo__btn mo__btn--danger" @click="submit">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h12v12H6z"/></svg>
            Stop &amp; Submit
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
  z-index: 1100;
  padding: 20px;
}
.mo {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  width: 480px; max-width: 100%;
  box-shadow: var(--shadow-md, 0 8px 24px rgba(0,0,0,0.15));
  animation: mo-in 0.18s cubic-bezier(0.34,1.56,0.64,1);
}
@keyframes mo-in { from { transform: scale(0.94); opacity: 0; } }

.mo__header {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 20px 20px 16px;
  border-bottom: 1px solid var(--border-color);
}
.mo__header-icon {
  width: 32px; height: 32px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; margin-top: 1px;
  background: var(--blue-50, #eff6ff); color: var(--primary);
}
.mo__header-icon--red { background: var(--red-50, #fef2f2); color: var(--red-600, #dc2626); }

.mo__title { margin: 0; font-size: 15px; font-weight: 700; color: var(--text-color); letter-spacing: -0.02em; }
.mo__subtitle { margin: 3px 0 0; font-size: 12px; color: var(--text-muted); }
.mo__close {
  margin-left: auto; background: none; border: none; color: var(--text-muted);
  cursor: pointer; padding: 4px; border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.12s, color 0.12s;
}
.mo__close:hover { background: var(--control-bg); color: var(--text-color); }

.mo__body { padding: 18px 20px; display: flex; flex-direction: column; gap: 16px; }
.mo__field { display: flex; flex-direction: column; gap: 4px; }
.mo__label { font-size: 13px; font-weight: 600; color: var(--text-color); }
.mo__req { color: var(--red-500, #ef4444); margin-left: 2px; }
.mo__hint { font-size: 12px; color: var(--text-muted); margin: 0; }
.mo__textarea {
  width: 100%; padding: 9px 12px;
  border: 1px solid var(--border-color); border-radius: 7px;
  background: var(--card-bg); color: var(--text-color);
  font-size: 13.5px; font-family: inherit; resize: vertical;
  transition: border-color 0.15s, box-shadow 0.15s;
  box-sizing: border-box;
}
.mo__textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }
.mo__input--datetime {
  width: 100%; padding: 9px 12px;
  border: 1px solid var(--border-color); border-radius: 7px;
  background: var(--card-bg); color: var(--text-color);
  font-size: 13.5px; font-family: inherit;
  transition: border-color 0.15s, box-shadow 0.15s;
  box-sizing: border-box;
}
.mo__input--datetime:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }
.mo__select {
  width: 100%; padding: 9px 12px;
  border: 1px solid var(--border-color); border-radius: 7px;
  background: var(--card-bg); color: var(--text-color);
  font-size: 13.5px; font-family: inherit;
  transition: border-color 0.15s, box-shadow 0.15s;
  box-sizing: border-box;
}
.mo__select:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }

/* Billable grid */
.mo__billable-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 6px;
  margin-top: 2px;
}
.mo__bill-opt {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 2px; padding: 9px 4px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--card-bg);
  cursor: pointer;
  transition: background 0.12s, border-color 0.12s;
  text-align: center;
}
.mo__bill-opt:hover { background: var(--control-bg); border-color: var(--gray-400, #9ca3af); }
.mo__bill-opt--active { background: var(--blue-50, #eff6ff); border-color: var(--primary); }
.mo__bill-pct { font-size: 14px; font-weight: 700; color: var(--text-color); }
.mo__bill-opt--active .mo__bill-pct { color: var(--primary); }
.mo__bill-hint { font-size: 9.5px; color: var(--text-muted); line-height: 1.2; }

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
.mo__btn--danger { background: var(--red-600, #dc2626); color: #fff; border-color: var(--red-600, #dc2626); }
.mo__btn--danger:hover { background: var(--red-700, #b91c1c); }
</style>
