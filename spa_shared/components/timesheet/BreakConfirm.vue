<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import {
	formatDurationShort,
	secondsSinceSystemDatetime,
} from "@iown/utils/datetime";

const props = defineProps({
  breakFrom: String,  // system-tz "YYYY-MM-DD HH:mm:ss"
});
const emit = defineEmits(["confirm", "skip", "close"]);

const liveNow = ref(new Date());
let interval = null;

onMounted(() => { interval = setInterval(() => { liveNow.value = new Date(); }, 1000); });
onUnmounted(() => clearInterval(interval));

const breakDuration = computed(() => {
  liveNow.value;
  if (!props.breakFrom) return "—";
  return formatDurationShort(secondsSinceSystemDatetime(props.breakFrom));
});

function onKey(e) {
  if (e.key === "Escape") emit("close");
  if (e.key === "Enter") emit("confirm");
}
</script>

<template>
  <div class="bc-backdrop" @click.self="emit('close')" @keydown="onKey">
    <div class="bc" role="dialog" aria-modal="true">
      <div class="bc__icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
        </svg>
      </div>

      <div class="bc__body">
        <h3 class="bc__title">Log break time?</h3>

        <div class="bc__dur-chip">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
            <path d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zm.01 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67V7z"/>
          </svg>
          {{ breakDuration }}
        </div>

        <p class="bc__desc">
          You've been on a break. Would you like to log this time as a separate timesheet entry?
          This helps track time spent on meetings, reviews, standups, or any other activity
          that happened during the pause — keeping your records accurate and billable where needed.
        </p>
      </div>

      <div class="bc__actions">
        <button class="bc__btn bc__btn--ghost" @click="emit('skip')">
          No, skip it
        </button>
        <button class="bc__btn bc__btn--amber" @click="emit('confirm')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
            <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
          </svg>
          Yes, log break
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bc-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.4);
  backdrop-filter: blur(3px);
  display: flex; align-items: center; justify-content: center;
  z-index: 1100; padding: 20px;
}
.bc {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  width: 400px; max-width: 100%;
  padding: 28px 28px 24px;
  box-shadow: var(--shadow-md, 0 8px 32px rgba(0,0,0,0.18));
  animation: bc-in 0.18s cubic-bezier(0.34,1.56,0.64,1);
  display: flex; flex-direction: column; align-items: center; text-align: center; gap: 0;
}
@keyframes bc-in { from { transform: scale(0.92); opacity: 0; } }

.bc__icon {
  width: 48px; height: 48px; border-radius: 12px;
  background: var(--yellow-50, #fefce8);
  color: var(--yellow-600, #ca8a04);
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 16px; flex-shrink: 0;
}

.bc__body { width: 100%; }

.bc__title {
  margin: 0 0 10px;
  font-size: 16px; font-weight: 700;
  color: var(--text-color); letter-spacing: -0.02em;
}

.bc__dur-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 12px;
  background: var(--yellow-50, #fefce8);
  border: 1px solid var(--yellow-200, #fef08a);
  border-radius: 20px;
  font-size: 13px; font-weight: 700;
  color: var(--yellow-700, #a16207);
  font-variant-numeric: tabular-nums;
  margin-bottom: 14px;
}

.bc__desc {
  font-size: 13px; line-height: 1.6;
  color: var(--text-muted);
  margin: 0;
}

.bc__actions {
  display: flex; gap: 10px; width: 100%;
  margin-top: 24px;
}
.bc__btn {
  flex: 1;
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  padding: 9px 16px; border-radius: 8px;
  font-size: 13px; font-weight: 600; cursor: pointer;
  border: 1px solid transparent; line-height: 1;
  transition: background 0.12s, border-color 0.12s;
}
.bc__btn--ghost { background: none; border-color: var(--border-color); color: var(--text-muted); }
.bc__btn--ghost:hover { background: var(--control-bg); color: var(--text-color); }
.bc__btn--amber { background: var(--yellow-500, #eab308); color: #1a1a1a; border-color: var(--yellow-500, #eab308); }
.bc__btn--amber:hover { background: var(--yellow-600, #ca8a04); border-color: var(--yellow-600, #ca8a04); }
</style>
