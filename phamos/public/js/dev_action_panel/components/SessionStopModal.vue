<script setup>
// Stop & submit the running timesheet from the sidebar session widget.
// Same fields and payload as the Stop panel on ProjectCard / IssueCard, so App.vue's
// onStop / onStopProjectTimer handle it unchanged.
// version-15 adaptation: no Value Add (#1744) and no End time field (the project Stop on
// version-15 has none either); the timesheet ends now. The card's Stop panel keeps its options.
import { ref, onMounted } from "vue";
import { RATING_OPTIONS, percentBillablePreset } from "../timesheetRating.js";

const props = defineProps({
  session: Object,
  isProject: Boolean,
});
const emit = defineEmits(["confirm", "cancel"]);

const activityTypes = ["Working Alone", "Working with Customer", "Working With Team"];
const t = {
  title: __("Stop & Submit Timesheet"),
  result: __("What did you accomplish?"),
  activity: __("Activity Type"),
  cancel: __("Cancel"),
  complete: __("Complete"),
};
const labels = {
  percentBillable: __("Percent Billable"),
};

const result = ref("");
const activityType = ref("");
// The project's preset: 100 for a customer project, 0 for phamos' own (#1896).
const percentBillable = ref(percentBillablePreset(props.session?.project_percent_billable));
const resultRef = ref(null);

onMounted(() => resultRef.value?.focus());

function submit() {
  if (!result.value.trim()) { frappe.msgprint(__("Please describe what you accomplished.")); return; }
  if (!activityType.value) { frappe.msgprint(__("Please select an Activity Type.")); return; }
  emit("confirm", {
    result: result.value.trim(),
    percentBillable: percentBillable.value,
    activityType: activityType.value,
  });
}

function onKey(e) {
  if (e.key === "Escape") emit("cancel");
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
}
</script>

<template>
  <div class="ssm-backdrop" @click.self="emit('cancel')" @keydown="onKey">
    <div class="ssm" role="dialog" aria-modal="true">
      <div class="ssm__header">
        <div class="ssm__icon">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h12v12H6z"/></svg>
        </div>
        <div class="ssm__heading">
          <h2 class="ssm__title">{{ t.title }}</h2>
          <p class="ssm__subtitle">
            <span v-if="isProject" class="ssm__type">Prj</span>
            {{ session?.goal || session?.project || "" }}
          </p>
        </div>
        <button class="ssm__close" :title="t.cancel" @click="emit('cancel')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </button>
      </div>

      <div class="ssm__body">
        <div class="ssm__field">
          <label class="ssm__label">{{ t.result }} <span class="ssm__req">*</span></label>
          <textarea ref="resultRef" v-model="result" class="ssm__input" rows="3" placeholder="Completed the task, resolved the issue…"></textarea>
        </div>

        <div class="ssm__row">
          <div class="ssm__field ssm__field--grow">
            <label class="ssm__label">{{ t.activity }} <span class="ssm__req">*</span></label>
            <select v-model="activityType" class="ssm__input">
              <option value="">— Select —</option>
              <option v-for="at in activityTypes" :key="at" :value="at">{{ at }}</option>
            </select>
          </div>
          <div class="ssm__field">
            <label class="ssm__label">{{ labels.percentBillable }}</label>
            <select v-model.number="percentBillable" class="ssm__input">
              <option v-for="v in RATING_OPTIONS" :key="v" :value="v">{{ v }}%</option>
            </select>
          </div>
        </div>
      </div>

      <div class="ssm__footer">
        <span class="ssm__kbd"><kbd>Ctrl</kbd><kbd>↵</kbd></span>
        <div class="ssm__actions">
          <button class="ssm__btn ssm__btn--ghost" @click="emit('cancel')">{{ t.cancel }}</button>
          <button class="ssm__btn ssm__btn--danger" @click="submit">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
            {{ t.complete }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ssm-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center;
  z-index: 1030; padding: 20px;
}
.ssm {
  background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px;
  width: 520px; max-width: 100%; max-height: calc(100vh - 40px); overflow-y: auto;
  box-shadow: var(--shadow-md, 0 8px 24px rgba(0,0,0,0.15));
}
.ssm__header { display: flex; align-items: flex-start; gap: 12px; padding: 18px 20px 14px; border-bottom: 1px solid var(--border-color); }
.ssm__icon {
  width: 30px; height: 30px; border-radius: 8px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: var(--red-50, #fef2f2); color: var(--red-600, #dc2626);
}
.ssm__heading { min-width: 0; flex: 1; }
.ssm__title { margin: 0; font-size: 15px; font-weight: 700; color: var(--text-color); }
.ssm__subtitle { margin: 3px 0 0; font-size: 12px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ssm__type { font-size: 10px; font-weight: 700; text-transform: uppercase; background: var(--blue-50, #eff6ff); color: var(--primary); border-radius: 3px; padding: 1px 5px; margin-right: 4px; }
.ssm__close { background: none; border: none; color: var(--text-muted); cursor: pointer; padding: 4px; border-radius: 4px; display: flex; }
.ssm__close:hover { background: var(--control-bg); color: var(--text-color); }
.ssm__body { padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }
.ssm__row { display: flex; gap: 10px; flex-wrap: wrap; }
.ssm__field { display: flex; flex-direction: column; gap: 4px; }
.ssm__field--grow { flex: 1; min-width: 160px; }
.ssm__label { font-size: 12px; font-weight: 600; color: var(--text-color); }
.ssm__req { color: var(--red-500, #ef4444); }
.ssm__optional { font-weight: 400; color: var(--text-muted); }
.ssm__hint { margin: -4px 0 0; font-size: 11px; color: var(--text-muted); }
.ssm__input {
  width: 100%; padding: 7px 10px; border: 1px solid var(--border-color); border-radius: 7px;
  background: var(--control-bg); color: var(--text-color); font-size: 13px; font-family: inherit; box-sizing: border-box;
}
textarea.ssm__input { resize: vertical; }
.ssm__input:focus { outline: none; border-color: var(--primary); }
.ssm__footer {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px; border-top: 1px solid var(--border-color); background: var(--bg-color); border-radius: 0 0 12px 12px;
}
.ssm__kbd { display: flex; gap: 3px; }
kbd { font-size: 10px; font-family: inherit; background: var(--control-bg); border: 1px solid var(--border-color); border-radius: 3px; padding: 1px 5px; color: var(--text-muted); }
.ssm__actions { display: flex; gap: 8px; }
.ssm__btn { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 7px; font-size: 13px; font-weight: 600; cursor: pointer; border: 1px solid transparent; }
.ssm__btn--ghost { background: none; border-color: var(--border-color); color: var(--text-muted); }
.ssm__btn--ghost:hover { background: var(--control-bg); color: var(--text-color); }
.ssm__btn--danger { background: var(--red-600, #dc2626); color: #fff; }
.ssm__btn--danger:hover { background: var(--red-700, #b91c1c); }
</style>
