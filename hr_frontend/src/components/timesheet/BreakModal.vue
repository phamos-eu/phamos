<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import { call } from "frappe-ui";
import {
	formatDurationShort,
	formatTime as formatBreakTime,
	secondsSinceSystemDatetime,
} from "@iown/utils/datetime";

const props = defineProps({
  breakFrom: String,  // system-tz "YYYY-MM-DD HH:mm:ss"
});
const emit = defineEmits(["confirm", "skip", "close"]);

const project = ref("");
const projectLabel = ref("");
const projectResults = ref([]);
const showDropdown = ref(false);
const goal = ref("");
const result = ref("");
const percentBillable = ref(0);
const activityType = ref("");
const goalRef = ref(null);
const liveNow = ref(new Date());

let liveInterval = null;
let searchTimer = null;

const ACTIVITY_TYPES = ["Working Alone", "Working with Customer", "Working With Team"];

const billableOptions = [
  { value: 100, label: "100%" },
  { value: 75,  label: "75%"  },
  { value: 50,  label: "50%"  },
  { value: 25,  label: "25%"  },
  { value: 0,   label: "0%"   },
];

onMounted(async () => {
  goalRef.value?.focus();
  liveInterval = setInterval(() => { liveNow.value = new Date(); }, 1000);
  await fetchProjects("");
});

onUnmounted(() => { clearInterval(liveInterval); clearTimeout(searchTimer); });

async function fetchProjects(term) {
  const filters = [["status", "=", "Open"]];
  if (term) filters.push(["project_name", "like", `%${term}%`]);
  const rows = await call("frappe.client.get_list", {
    doctype: "Project",
    filters,
    fields: ["name", "project_name"],
    limit: 50,
    order_by: "project_name asc",
  });
  projectResults.value = rows || [];
}

function onSearchInput() {
  project.value = "";
  showDropdown.value = true;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => fetchProjects(projectLabel.value), 300);
}

function onSearchFocus() {
  showDropdown.value = true;
  if (!projectResults.value.length) fetchProjects(projectLabel.value);
}

function onSearchBlur() {
  setTimeout(() => { showDropdown.value = false; }, 150);
}

function selectProject(p) {
  project.value = p.name;
  projectLabel.value = p.project_name || p.name;
  showDropdown.value = false;
}

const breakDuration = computed(() => {
  liveNow.value;
  if (!props.breakFrom) return "";
  return formatDurationShort(secondsSinceSystemDatetime(props.breakFrom));
});

function fmtTime(str) {
  return formatBreakTime(str);
}

const error = ref("");

function submit() {
  error.value = "";
  if (!project.value)        { error.value = "Please select a project."; return; }
  if (!activityType.value)   { error.value = "Please select an Activity Type."; return; }
  if (!goal.value.trim())    { error.value = "Please enter a goal."; return; }
  if (!result.value.trim())  { error.value = "Please describe what you did during the break."; return; }
  emit("confirm", {
    project: project.value,
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
        <div class="mo__header-icon mo__header-icon--amber">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
          </svg>
        </div>
        <div class="mo__header-text">
          <h2 class="mo__title">Log Break Time</h2>
          <p class="mo__subtitle">
            Started at <strong>{{ fmtTime(breakFrom) }}</strong>
            <span class="mo__dur"> · {{ breakDuration }}</span>
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
        <!-- Row 1: Project + Activity Type -->
        <div class="mo__row">
          <div class="mo__field mo__field--half">
            <label class="mo__label">Project <span class="mo__req">*</span></label>
            <p class="mo__hint">Which project was this break for?</p>
            <div class="mo__search-wrap">
              <input
                v-model="projectLabel"
                class="mo__search-input"
                placeholder="Search project..."
                autocomplete="off"
                @input="onSearchInput"
                @focus="onSearchFocus"
                @blur="onSearchBlur"
              />
              <ul v-if="showDropdown && projectResults.length" class="mo__dropdown">
                <li
                  v-for="p in projectResults"
                  :key="p.name"
                  class="mo__dropdown-item"
                  @mousedown.prevent="selectProject(p)"
                >
                  {{ p.project_name || p.name }}
                </li>
              </ul>
              <div v-else-if="showDropdown && projectLabel" class="mo__dropdown mo__dropdown--empty">
                No projects found
              </div>
            </div>
          </div>

          <div class="mo__field mo__field--half">
            <label class="mo__label">Activity Type <span class="mo__req">*</span></label>
            <p class="mo__hint">Type of work done</p>
            <select v-model="activityType" class="mo__select">
              <option value="">— Select type —</option>
              <option v-for="t in ACTIVITY_TYPES" :key="t" :value="t">{{ t }}</option>
            </select>
          </div>
        </div>

        <!-- Goal: full width -->
        <div class="mo__field">
          <label class="mo__label">Goal <span class="mo__req">*</span></label>
          <p class="mo__hint">What were you doing?</p>
          <textarea
            ref="goalRef"
            v-model="goal"
            class="mo__textarea"
            rows="2"
            placeholder="e.g. Team standup, reviewed PR comments"
          ></textarea>
        </div>

        <!-- Result: full width -->
        <div class="mo__field">
          <label class="mo__label">Result <span class="mo__req">*</span></label>
          <p class="mo__hint">What was the outcome?</p>
          <textarea
            v-model="result"
            class="mo__textarea"
            rows="2"
            placeholder="e.g. Discussed blockers, clarified requirements"
          ></textarea>
        </div>

        <!-- Billable %: horizontal buttons -->
        <div class="mo__field">
          <label class="mo__label">Billable %</label>
          <p class="mo__hint">How much of this break is billable?</p>
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
        <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
      </div>

      <!-- Footer -->
      <div class="mo__footer">
        <span class="mo__kbd-hint"><kbd>Ctrl</kbd><kbd>↵</kbd> to submit</span>
        <div class="mo__actions">
          <button class="mo__btn mo__btn--ghost" @click="emit('skip')">Skip</button>
          <button class="mo__btn mo__btn--amber" @click="submit">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
            Log Break
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
.mo__header-icon--amber { background: var(--yellow-50, #fefce8); color: var(--yellow-600, #ca8a04); }
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

.mo__search-wrap { position: relative; }
.mo__search-input {
  width: 100%; padding: 8px 12px;
  border: 1px solid var(--border-color); border-radius: 7px;
  background: var(--card-bg); color: var(--text-color);
  font-size: 13.5px; font-family: inherit;
  transition: border-color 0.15s, box-shadow 0.15s;
  box-sizing: border-box;
}
.mo__search-input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }
.mo__dropdown {
  position: absolute; top: calc(100% + 4px); left: 0; right: 0;
  background: var(--card-bg); border: 1px solid var(--border-color);
  border-radius: 7px; max-height: 200px; overflow-y: auto;
  z-index: 10; box-shadow: 0 4px 12px rgba(0,0,0,0.12);
  list-style: none; margin: 0; padding: 4px 0;
}
.mo__dropdown-item {
  padding: 8px 12px; font-size: 13px; cursor: pointer; color: var(--text-color);
}
.mo__dropdown-item:hover { background: var(--control-bg); }
.mo__dropdown--empty { padding: 8px 12px; font-size: 13px; color: var(--text-muted); }

.mo__select {
  width: 100%; padding: 8px 12px;
  border: 1px solid var(--border-color); border-radius: 7px;
  background: var(--card-bg); color: var(--text-color);
  font-size: 13.5px; font-family: inherit;
  transition: border-color 0.15s, box-shadow 0.15s;
  box-sizing: border-box;
}
.mo__select:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }
.mo__textarea {
  width: 100%; padding: 8px 12px;
  border: 1px solid var(--border-color); border-radius: 7px;
  background: var(--card-bg); color: var(--text-color);
  font-size: 13.5px; font-family: inherit; resize: vertical;
  transition: border-color 0.15s, box-shadow 0.15s;
  box-sizing: border-box;
}
.mo__textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }

.mo__billable-row { display: flex; gap: 6px; margin-top: 2px; }
.mo__bill-opt {
  flex: 1;
  padding: 7px 4px;
  border: 1px solid var(--border-color); border-radius: 6px;
  background: var(--card-bg); cursor: pointer;
  font-size: 13px; font-weight: 700; color: var(--text-color);
  transition: background 0.12s, border-color 0.12s; text-align: center;
}
.mo__bill-opt:hover { background: var(--control-bg); border-color: var(--gray-400, #9ca3af); }
.mo__bill-opt--active { background: var(--yellow-50, #fefce8); border-color: var(--yellow-500, #eab308); color: var(--yellow-700, #a16207); }

.mo__footer {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px;
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
.mo__btn--amber { background: var(--yellow-500, #eab308); color: #1a1a1a; border-color: var(--yellow-500, #eab308); }
.mo__btn--amber:hover { background: var(--yellow-600, #ca8a04); border-color: var(--yellow-600, #ca8a04); }
</style>
