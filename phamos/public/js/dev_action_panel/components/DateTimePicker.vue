<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from "vue";

const props = defineProps({
  modelValue:  { type: Date,    default: () => new Date() },
  dateFormat:  { type: String,  default: "dd.mm.yyyy" },
  timeFormat:  { type: String,  default: "HH:mm:ss" },
  autoUpdate:  { type: Boolean, default: false },
  timezone:    { type: String,  default: "" },
});
const emit = defineEmits(["update:modelValue"]);

const open       = ref(false);
const triggerRef = ref(null);
const popupRef   = ref(null);
const popupStyle = ref({});

// Live clock (only runs when autoUpdate=true)
// Returns a Date whose getHours()/getMinutes() equal the user-tz current time
function userNow() {
  const tz = frappe.boot?.time_zone?.user;
  if (tz && typeof moment !== "undefined" && moment.tz) {
    try {
      const m = moment().tz(tz);
      return new Date(m.year(), m.month(), m.date(), m.hour(), m.minute(), m.second());
    } catch(e) {}
  }
  return new Date();
}

const liveNow = ref(userNow());
let liveInterval = null;

watch(() => props.autoUpdate, (val) => {
  if (val && !liveInterval) {
    liveInterval = setInterval(() => { liveNow.value = userNow(); }, 1000);
  } else if (!val && liveInterval) {
    clearInterval(liveInterval); liveInterval = null;
  }
}, { immediate: true });

// Picker internal state
const selected = ref(new Date(props.modelValue));
const viewYear = ref(selected.value.getFullYear());
const viewMonth = ref(selected.value.getMonth());
const timeH = ref(selected.value.getHours());
const timeM = ref(selected.value.getMinutes());

watch(() => props.modelValue, (val) => {
  if (val instanceof Date && !isNaN(val) && !open.value) {
    selected.value = new Date(val);
    viewYear.value  = val.getFullYear();
    viewMonth.value = val.getMonth();
    timeH.value = val.getHours();
    timeM.value = val.getMinutes();
  }
}, { immediate: false });

const showSeconds = computed(() => props.timeFormat?.includes("ss"));

const MONTHS    = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"];
const DAY_NAMES = ["Mo","Tu","We","Th","Fr","Sa","Su"];

const monthLabel = computed(() => `${MONTHS[viewMonth.value]} ${viewYear.value}`);

const calendarDays = computed(() => {
  const days = [];
  const startOffset = (new Date(viewYear.value, viewMonth.value, 1).getDay() - 1 + 7) % 7;
  for (let i = startOffset; i > 0; i--)
    days.push({ date: new Date(viewYear.value, viewMonth.value, 1 - i), thisMonth: false });
  const daysInMonth = new Date(viewYear.value, viewMonth.value + 1, 0).getDate();
  for (let d = 1; d <= daysInMonth; d++)
    days.push({ date: new Date(viewYear.value, viewMonth.value, d), thisMonth: true });
  for (let d = 1; days.length < 42; d++)
    days.push({ date: new Date(viewYear.value, viewMonth.value + 1, d), thisMonth: false });
  return days;
});

function isSameDay(a, b) {
  return a.getFullYear() === b.getFullYear() &&
         a.getMonth()    === b.getMonth()    &&
         a.getDate()     === b.getDate();
}
function isToday(date)    { return isSameDay(date, new Date()); }
function isSelected(date) { return isSameDay(date, selected.value); }
function clamp(v, min, max) { return Math.min(max, Math.max(min, Number(v) || 0)); }

function pad(n) { return String(n).padStart(2, "0"); }

function formatDisplay(date, h, m, s) {
  if (!date) return "";
  const dd = pad(date.getDate()), mo = pad(date.getMonth() + 1), y = date.getFullYear();
  const datePart = props.dateFormat.replace("dd", dd).replace("mm", mo).replace("yyyy", y);
  const timePart = showSeconds.value
    ? `${pad(clamp(h,0,23))}:${pad(clamp(m,0,59))}:${pad(clamp(s||0,0,59))}`
    : `${pad(clamp(h,0,23))}:${pad(clamp(m,0,59))}`;
  return `${datePart} ${timePart}`;
}

// Trigger display: live clock when autoUpdate and popup closed
const displayValue = computed(() => {
  if (props.autoUpdate && !open.value) {
    const n = liveNow.value;
    return formatDisplay(n, n.getHours(), n.getMinutes(), n.getSeconds());
  }
  return formatDisplay(selected.value, timeH.value, timeM.value, 0);
});

function emitCurrent() {
  const d = new Date(selected.value);
  d.setHours(clamp(timeH.value, 0, 23), clamp(timeM.value, 0, 59), 0, 0);
  emit("update:modelValue", d);
}

function selectDay(day) {
  selected.value = new Date(day.date.getFullYear(), day.date.getMonth(), day.date.getDate(),
    timeH.value, timeM.value, 0);
  viewYear.value  = day.date.getFullYear();
  viewMonth.value = day.date.getMonth();
  emitCurrent();
}

function prevMonth() {
  if (viewMonth.value === 0) { viewMonth.value = 11; viewYear.value--; }
  else viewMonth.value--;
}
function nextMonth() {
  if (viewMonth.value === 11) { viewMonth.value = 0; viewYear.value++; }
  else viewMonth.value++;
}

// Allow only digit keys during typing; clamp + pad on blur
function onTimeKeydown(e) {
  const allowed = ["Backspace","Delete","Tab","ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Home","End"];
  if (!allowed.includes(e.key) && !/^\d$/.test(e.key)) e.preventDefault();
}
function onHourBlur(e) {
  timeH.value = clamp(parseInt(e.target.value) || 0, 0, 23);
  e.target.value = pad(timeH.value);
  emitCurrent();
}
function onMinBlur(e) {
  timeM.value = clamp(parseInt(e.target.value) || 0, 0, 59);
  e.target.value = pad(timeM.value);
  emitCurrent();
}

async function openPicker() {
  // Initialise from live clock so user starts from "now"
  const base = props.autoUpdate ? userNow() : selected.value;
  selected.value  = new Date(base);
  viewYear.value  = base.getFullYear();
  viewMonth.value = base.getMonth();
  timeH.value = base.getHours();
  timeM.value = base.getMinutes();

  open.value = true;
  await nextTick();
  if (!triggerRef.value) return;

  const rect = triggerRef.value.getBoundingClientRect();
  const W = 252, H_POPUP = 360;
  let left = rect.left;
  let top  = rect.bottom + 4;
  if (left + W > window.innerWidth  - 8) left = window.innerWidth  - W - 8;
  if (top  + H_POPUP > window.innerHeight - 8) top = rect.top - H_POPUP - 4;
  popupStyle.value = { position: "fixed", top: `${top}px`, left: `${left}px`,
                       width: `${W}px`, zIndex: "10000" };
}

function toggle() {
  if (open.value) { open.value = false; } else { openPicker(); }
}

function onOutside(e) {
  if (!triggerRef.value?.contains(e.target) && !popupRef.value?.contains(e.target))
    open.value = false;
}
onMounted(()   => document.addEventListener("mousedown", onOutside));
onUnmounted(() => {
  document.removeEventListener("mousedown", onOutside);
  if (liveInterval) clearInterval(liveInterval);
});
</script>

<template>
  <div ref="triggerRef">
    <div class="dtp__trigger" @click="toggle">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" class="dtp__icon">
        <path d="M19 3h-1V1h-2v2H8V1H6v2H5C3.89 3 3.01 3.9 3.01 5L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7z"/>
      </svg>
      <span class="dtp__val">{{ displayValue }}</span>
    </div>

    <Teleport to="body">
      <Transition name="dtp-pop">
        <div v-if="open" ref="popupRef" class="dtp__popup" :style="popupStyle" @click.stop>

          <div class="dtp__nav">
            <button class="dtp__nav-btn" @click="prevMonth">&#8249;</button>
            <span class="dtp__month-lbl">{{ monthLabel }}</span>
            <button class="dtp__nav-btn" @click="nextMonth">&#8250;</button>
          </div>

          <div class="dtp__grid">
            <span v-for="d in DAY_NAMES" :key="d" class="dtp__dayname">{{ d }}</span>
            <button
              v-for="(day, i) in calendarDays" :key="i"
              class="dtp__day"
              :class="{
                'dtp__day--other': !day.thisMonth,
                'dtp__day--today': isToday(day.date),
                'dtp__day--sel':   isSelected(day.date),
              }"
              @click="selectDay(day)"
            >{{ day.date.getDate() }}</button>
          </div>

          <div class="dtp__time">
            <span class="dtp__time-lbl">Time</span>
            <input
              type="text" inputmode="numeric"
              :value="pad(clamp(timeH, 0, 23))"
              @keydown="onTimeKeydown" @blur="onHourBlur"
              maxlength="2" class="dtp__time-in"
            />
            <span class="dtp__colon">:</span>
            <input
              type="text" inputmode="numeric"
              :value="pad(clamp(timeM, 0, 59))"
              @keydown="onTimeKeydown" @blur="onMinBlur"
              maxlength="2" class="dtp__time-in"
            />
            <span v-if="showSeconds" class="dtp__colon">:</span>
            <span v-if="showSeconds" class="dtp__time-sec">00</span>
          </div>

        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.dtp__trigger {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 6px 10px;
  border: 1px solid var(--border-color); border-radius: 6px;
  background: var(--card-bg); color: var(--text-color);
  cursor: pointer; font-size: 13px; font-family: inherit;
  transition: border-color 0.15s;
  width: 100%; box-sizing: border-box;
}
.dtp__trigger:hover { border-color: var(--primary); }
.dtp__icon { color: var(--text-muted); flex-shrink: 0; }
.dtp__val  { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
             font-family: var(--font-monospace, monospace); font-size: 12.5px; }
</style>

<style>
.dtp__popup {
  background: var(--card-bg); border: 1px solid var(--border-color);
  border-radius: 10px; padding: 14px 16px;
  box-shadow: 0 8px 28px rgba(0,0,0,0.22);
}

.dtp__nav {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;
}
.dtp__nav-btn {
  background: none; border: none; cursor: pointer;
  font-size: 20px; line-height: 1; padding: 0 6px;
  color: var(--text-muted); border-radius: 4px;
}
.dtp__nav-btn:hover { background: var(--control-bg); color: var(--text-color); }
.dtp__month-lbl { font-size: 13px; font-weight: 700; color: var(--text-color); }

.dtp__grid {
  display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; margin-bottom: 10px;
}
.dtp__dayname {
  font-size: 10px; font-weight: 700; color: var(--text-muted);
  text-align: center; padding: 3px 0;
}
.dtp__day {
  aspect-ratio: 1; display: flex; align-items: center; justify-content: center;
  font-size: 12px; border: none; background: none; border-radius: 5px;
  cursor: pointer; color: var(--text-color); transition: background 0.1s;
  font-family: inherit;
}
.dtp__day:hover:not(.dtp__day--sel) { background: var(--control-bg); }
.dtp__day--other { color: var(--text-muted); opacity: 0.4; }
.dtp__day--today { font-weight: 700; color: var(--primary); }
.dtp__day--sel   { background: var(--primary) !important; color: #fff !important; }

.dtp__time {
  display: flex; align-items: center; gap: 6px;
  padding-top: 12px; margin-top: 2px; border-top: 1px solid var(--border-color);
}
.dtp__time-lbl {
  font-size: 11px; font-weight: 700; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.05em; margin-right: 4px;
}
.dtp__time-in {
  width: 46px; text-align: center; padding: 6px 4px;
  border: 1px solid var(--border-color); border-radius: 6px;
  background: var(--card-bg); color: var(--text-color);
  font-size: 14px; font-family: var(--font-monospace, monospace);
  transition: border-color 0.15s;
}
.dtp__time-in:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 2px rgba(37,99,235,0.1); }
.dtp__colon   { font-size: 16px; font-weight: 700; color: var(--text-muted); }
.dtp__time-sec {
  font-size: 14px; font-family: var(--font-monospace, monospace);
  color: var(--text-muted); min-width: 24px; text-align: center;
}

.dtp-pop-enter-active { transition: opacity 0.14s ease, transform 0.14s ease; }
.dtp-pop-leave-active { transition: opacity 0.10s ease, transform 0.10s ease; }
.dtp-pop-enter-from, .dtp-pop-leave-to { opacity: 0; transform: translateY(-4px) scale(0.98); }
</style>
