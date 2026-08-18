<script setup>
import { ref, computed } from "vue";

const props = defineProps({
  project: Object,
  mode: String, // 'my' | 'all'
  activeProjectSession: Object,
  projectElapsedSeconds: Number,
  activeIssueSession: Object,
});

const emit = defineEmits(["start", "pause", "resume", "stop", "assign"]);

const panel = ref(null); // null | 'start' | 'stop'
const sessionsOpen = ref(false);
const sessions = ref([]);
const loadingSessions = ref(false);

const startGoal = ref("");
const expectedHours = ref(1);
const stopResult = ref("");
const stopBillable = ref(100);
const stopActivityType = ref("");
const activityTypes = ["Working Alone", "Working with Customer", "Working With Team"];

const isActive = computed(() => props.activeProjectSession?.project === props.project.name);
const sessionState = computed(() => isActive.value ? props.activeProjectSession?.session_state : null);
const hasAnySession = computed(() => !!props.activeProjectSession || !!props.activeIssueSession);

function fmtElapsed(s) {
  s = Math.max(0, s || 0);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
}
function fmtDuration(s) {
  if (!s) return "—";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}
function fmtDate(dtStr) {
  if (!dtStr) return "—";
  const parts = dtStr.split(/[- :]/).map(Number);
  if (parts.length < 3) return dtStr;
  const [y, mo, dd] = parts;
  return new Date(y, mo - 1, dd).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

async function toggleSessions() {
  sessionsOpen.value = !sessionsOpen.value;
  if (sessionsOpen.value && !sessions.value.length) {
    loadingSessions.value = true;
    const r = await frappe.call({
      method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_project_timesheets",
      args: { project_name: props.project.name },
    });
    sessions.value = r.message || [];
    loadingSessions.value = false;
  }
}

function openStart() { panel.value = panel.value === "start" ? null : "start"; }
function openStop()  { panel.value = panel.value === "stop"  ? null : "stop"; }
function closePanel() { panel.value = null; }

function confirmStart() {
  if (!expectedHours.value || expectedHours.value < 0.25) { frappe.msgprint(__("Minimum 0.25h")); return; }
  emit("start", {
    project: props.project,
    expectedTime: Math.round(parseFloat(expectedHours.value) * 3600),
    goal: startGoal.value.trim() || props.project.project_name,
  });
  panel.value = null;
  startGoal.value = "";
}

function confirmStop() {
  if (!stopResult.value.trim()) { frappe.msgprint(__("Please describe what you accomplished.")); return; }
  if (!stopActivityType.value) { frappe.msgprint(__("Please select an Activity Type.")); return; }
  emit("stop", { result: stopResult.value.trim(), percentBillable: stopBillable.value, activityType: stopActivityType.value });
  panel.value = null;
  stopResult.value = "";
  stopActivityType.value = "";
}

function onStartKey(e) { if (e.key === "Escape") closePanel(); if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) confirmStart(); }
function onStopKey(e)  { if (e.key === "Escape") closePanel(); if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) confirmStop(); }
</script>

<template>
  <div
    class="pc"
    :class="{
      'pc--active':  isActive,
      'pc--running': sessionState === 'running',
      'pc--paused':  sessionState === 'paused',
      'pc--blocked': hasAnySession && !isActive && mode === 'my',
    }"
  >
    <div class="pc__body">
      <div class="pc__side">
        <span class="pc__dot" :class="{
          'dot--idle':    !isActive,
          'dot--running': sessionState === 'running',
          'dot--paused':  sessionState === 'paused',
        }"></span>
      </div>

      <div class="pc__content">
        <div class="pc__meta">
          <span class="pc__customer">{{ project.customer_desc || project.customer || '—' }}</span>
          <span class="pc__flex"></span>
          <span class="pc__status">{{ project.status }}</span>
        </div>

        <div class="pc__title-row">
          <a :href="`/app/project/${project.name}`" target="_blank" class="pc__title">{{ project.project_name }}</a>
          <a :href="`/app/project/${project.name}`" target="_blank" class="pc__ext-link" title="Open project">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg>
          </a>
        </div>

        <div class="pc__info">
          <!-- Assignee chips (up to 4) -->
          <span
            v-for="a in (project.assignees || []).slice(0, 4)"
            :key="a.user"
            class="pc__assignee"
            :title="a.full_name || a.user"
          >{{ a.initial }}</span>
          <!-- Tracked time -->
          <span v-if="project.total_tracked_seconds" class="pc__info-item pc__info-item--tracked">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="pc__info-icon"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            {{ fmtDuration(project.total_tracked_seconds) }}
          </span>
          <span class="pc__info-flex"></span>

          <template v-if="mode === 'my'">
            <span v-if="isActive" class="pc__timer" :class="sessionState === 'running' ? 'timer--green' : 'timer--amber'">
              {{ fmtElapsed(projectElapsedSeconds) }}
            </span>
            <button v-if="!hasAnySession" class="pc__btn pc__btn--start" :class="{ 'pc__btn--open': panel === 'start' }" @click="openStart">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
              Start
            </button>
            <template v-else-if="isActive">
              <button v-if="sessionState === 'running'" class="pc__btn pc__btn--pause" @click="emit('pause')">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                Pause
              </button>
              <button v-else class="pc__btn pc__btn--resume" @click="emit('resume')">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                Resume
              </button>
              <button class="pc__btn pc__btn--stop" :class="{ 'pc__btn--open': panel === 'stop' }" @click="openStop">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h12v12H6z"/></svg>
                Stop
              </button>
            </template>
            <button v-else class="pc__btn pc__btn--muted" disabled title="Another timer is running">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
              Start
            </button>
          </template>

          <template v-else>
            <button
              v-if="!project.is_assigned"
              class="pc__btn pc__btn--assign"
              @click="emit('assign', project)"
            >
              Assign to me
            </button>
            <span v-else class="pc__assigned-badge">Assigned</span>
          </template>
        </div>
      </div>
    </div>

    <!-- Start panel -->
    <Transition name="panel">
      <div v-if="panel === 'start'" class="pc__panel pc__panel--start" @keydown="onStartKey">
        <div class="pc__panel-inner">
          <div class="pc__panel-row pc__panel-row--top">
            <div class="pc__panel-field">
              <label class="pc__panel-label">Expected time</label>
              <div class="pc__panel-input-row">
                <input v-model.number="expectedHours" type="number" min="0.25" step="0.25" class="pc__panel-input pc__panel-input--sm" autofocus />
                <span class="pc__panel-unit">hours</span>
              </div>
            </div>
            <div class="pc__panel-field pc__panel-field--grow">
              <label class="pc__panel-label">Goal</label>
              <input v-model="startGoal" type="text" class="pc__panel-input pc__panel-input--full" :placeholder="project.project_name" />
            </div>
          </div>
          <div class="pc__panel-actions">
            <button class="pc__panel-btn pc__panel-btn--ghost" @click="closePanel">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
              Cancel
            </button>
            <button class="pc__panel-btn pc__panel-btn--primary" @click="confirmStart">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
              Begin
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Stop panel -->
    <Transition name="panel">
      <div v-if="panel === 'stop'" class="pc__panel pc__panel--stop" @keydown="onStopKey">
        <div class="pc__panel-inner">
          <div class="pc__panel-field pc__panel-field--full">
            <label class="pc__panel-label">What did you accomplish? <span class="pc__panel-required">*</span></label>
            <textarea v-model="stopResult" class="pc__panel-textarea" rows="2" placeholder="Completed the task, resolved the issue…" autofocus></textarea>
          </div>
          <div class="pc__panel-row">
            <div class="pc__panel-field">
              <label class="pc__panel-label">Activity Type <span class="pc__panel-required">*</span></label>
              <select v-model="stopActivityType" class="pc__panel-select pc__panel-select--full">
                <option value="">— Select —</option>
                <option v-for="at in activityTypes" :key="at" :value="at">{{ at }}</option>
              </select>
            </div>
            <div class="pc__panel-field">
              <label class="pc__panel-label">Billable %</label>
              <select v-model.number="stopBillable" class="pc__panel-select">
                <option :value="100">100%</option>
                <option :value="75">75%</option>
                <option :value="50">50%</option>
                <option :value="25">25%</option>
                <option :value="0">0% — Internal</option>
              </select>
            </div>
            <div class="pc__panel-actions pc__panel-actions--end">
              <button class="pc__panel-btn pc__panel-btn--ghost" @click="closePanel">Cancel</button>
              <button class="pc__panel-btn pc__panel-btn--danger" @click="confirmStop">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
                Complete
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Sessions -->
    <div v-if="project.timesheet_count > 0" class="pc__sessions">
      <button class="pc__sessions-toggle" @click="toggleSessions">
        <svg class="pc__sessions-chevron" :class="{ rotated: sessionsOpen }" width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M7 10l5 5 5-5z"/></svg>
        {{ project.timesheet_count }} {{ project.timesheet_count === 1 ? 'session' : 'sessions' }}
        <span class="pc__sessions-badge">tracked</span>
      </button>
      <Transition name="panel">
        <div v-if="sessionsOpen" class="pc__sessions-list">
          <div v-if="loadingSessions" class="pc__sessions-loading">Loading…</div>
          <div v-else-if="!sessions.length" class="pc__sessions-loading">No records found.</div>
          <div v-for="s in sessions" :key="s.name" class="pc__session-row">
            <div class="pc__session-left">
              <span class="pc__session-date">{{ fmtDate(s.from_time) }}</span>
              <span class="pc__session-dur">{{ fmtDuration(s.actual_time) }}</span>
              <span class="pc__session-status" :class="s.docstatus === 1 ? 'status--submitted' : 'status--draft'">
                {{ s.docstatus === 1 ? 'Submitted' : 'Draft' }}
              </span>
            </div>
            <div class="pc__session-result">{{ s.result || s.goal || '—' }}</div>
            <a :href="`/app/timesheet-record/${s.name}`" target="_blank" class="pc__session-link" title="Open record">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg>
            </a>
          </div>
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
/* ── Base card ─────────────────────────────────────────────────── */
.pc {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  overflow: hidden;
  transition: box-shadow 0.15s, border-color 0.15s;
}
.pc:hover { box-shadow: 0 1px 6px rgba(0,0,0,0.07); border-color: var(--gray-300, #d1d5db); }
.pc--active  { border-color: var(--primary); }
.pc--running { box-shadow: 0 0 0 3px rgba(37,99,235,0.08); }
.pc--blocked { opacity: 0.72; }

/* ── Body ──────────────────────────────────────────────────────── */
.pc__body { display: flex; }

.pc__side {
  display: flex; align-items: flex-start;
  padding: 14px 0 14px 13px; flex-shrink: 0;
}
.pc--running .pc__side { border-left: 3px solid var(--green-500, #22c55e); padding-left: 10px; }
.pc--paused  .pc__side { border-left: 3px solid var(--yellow-500, #eab308); padding-left: 10px; }

.pc__dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 2px; flex-shrink: 0; transition: background 0.2s; }
.dot--idle    { background: var(--gray-300, #d1d5db); }
.dot--running { background: var(--green-500, #22c55e); box-shadow: 0 0 0 3px rgba(34,197,94,0.2); animation: pulse 2s ease-in-out infinite; }
.dot--paused  { background: var(--yellow-500, #eab308); }
@keyframes pulse { 0%,100% { box-shadow: 0 0 0 3px rgba(34,197,94,0.2); } 50% { box-shadow: 0 0 0 5px rgba(34,197,94,0.06); } }

.pc__content { flex: 1; min-width: 0; padding: 10px 13px 10px 8px; display: flex; flex-direction: column; gap: 4px; }

/* ── Meta ──────────────────────────────────────────────────────── */
.pc__meta { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted); }
.pc__customer { font-size: 11.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pc__flex { flex: 1; }
.pc__status {
  font-size: 10.5px; font-weight: 600; padding: 2px 7px; border-radius: 10px;
  background: var(--control-bg); color: var(--text-muted); white-space: nowrap;
}

/* ── Title ─────────────────────────────────────────────────────── */
.pc__title-row { display: flex; align-items: flex-start; gap: 6px; }
.pc__title {
  flex: 1; font-size: 13.5px; font-weight: 500; color: var(--text-color);
  text-decoration: none; line-height: 1.4; letter-spacing: -0.01em;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pc__title:hover { color: var(--primary); text-decoration: underline; }
.pc__ext-link { color: var(--text-muted); flex-shrink: 0; display: flex; align-items: center; opacity: 0.5; transition: opacity 0.1s; margin-top: 2px; }
.pc__ext-link:hover { opacity: 1; }

/* ── Info / action row ─────────────────────────────────────────── */
.pc__info { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 5px; }
.pc__info-flex { flex: 1; min-width: 4px; }
.pc__timer { font-family: var(--font-monospace, monospace); font-size: 12px; font-weight: 700; letter-spacing: 0.04em; white-space: nowrap; }
.timer--green { color: var(--green-600, #16a34a); }
.timer--amber { color: var(--yellow-600, #ca8a04); }

/* ── Buttons ───────────────────────────────────────────────────── */
.pc__btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 11px; border-radius: 6px; font-size: 12px; font-weight: 600;
  cursor: pointer; border: 1px solid transparent;
  transition: background 0.12s, border-color 0.12s;
  white-space: nowrap; line-height: 1;
}
.pc__btn--start  { background: #15803d; color: #fff; border-color: #15803d; }
.pc__btn--start:hover, .pc__btn--start.pc__btn--open { background: #166534; border-color: #166534; }
.pc__btn--pause  { background: var(--yellow-50, #fefce8); color: var(--yellow-700, #a16207); border-color: var(--yellow-200, #fef08a); }
.pc__btn--pause:hover { background: var(--yellow-100, #fef9c3); }
.pc__btn--resume { background: var(--green-50, #f0fdf4); color: var(--green-700, #15803d); border-color: var(--green-200, #bbf7d0); }
.pc__btn--resume:hover { background: var(--green-100, #dcfce7); }
.pc__btn--stop   { background: var(--red-50, #fef2f2); color: var(--red-600, #dc2626); border-color: var(--red-200, #fecaca); }
.pc__btn--stop:hover, .pc__btn--stop.pc__btn--open { background: var(--red-100, #fee2e2); border-color: var(--red-400, #f87171); }
.pc__btn--muted  { background: var(--control-bg); color: var(--text-muted); border-color: var(--border-color); cursor: not-allowed; opacity: 0.55; }
.pc__btn--assign { background: var(--control-bg); color: var(--text-color); border-color: var(--border-color); }
.pc__btn--assign:hover { background: var(--primary); color: #fff; border-color: var(--primary); }
.pc__assigned-badge { font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 10px; background: var(--green-50, #f0fdf4); color: var(--green-700, #15803d); border: 1px solid var(--green-200, #bbf7d0); white-space: nowrap; }

/* ── Info row extras ───────────────────────────────────────────── */
.pc__info { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; margin-top: 5px; }
.pc__info-flex { flex: 1; min-width: 4px; }
.pc__info-item { display: inline-flex; align-items: center; gap: 4px; font-size: 11.5px; color: var(--text-muted); white-space: nowrap; }
.pc__info-item--tracked { color: #16a34a; font-weight: 600; }
.pc__info-icon { flex-shrink: 0; opacity: 0.7; }
.pc__assignee {
  display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; border-radius: 50%;
  background: var(--primary); color: #fff;
  font-size: 10px; font-weight: 700; flex-shrink: 0;
  border: 1.5px solid var(--card-bg);
}

/* ── Sessions ──────────────────────────────────────────────────── */
.pc__sessions { border-top: 1px solid var(--border-color); }
.pc__sessions-toggle {
  display: flex; align-items: center; gap: 5px;
  width: 100%; padding: 7px 14px; border: none; background: transparent;
  color: var(--text-muted); font-size: 12px; cursor: pointer; text-align: left;
}
.pc__sessions-toggle:hover { background: var(--control-bg); color: var(--text-color); }
.pc__sessions-chevron { transition: transform 0.18s; flex-shrink: 0; }
.pc__sessions-chevron.rotated { transform: rotate(180deg); }
.pc__sessions-badge { font-size: 10px; font-weight: 700; background: var(--control-bg); border-radius: 3px; padding: 1px 5px; text-transform: uppercase; letter-spacing: 0.04em; }
.pc__sessions-list { background: var(--bg-color); border-top: 1px solid var(--border-color); }
.pc__sessions-loading { padding: 8px 14px; font-size: 12px; color: var(--text-muted); }
.pc__session-row { display: flex; align-items: center; gap: 8px; padding: 6px 14px; border-bottom: 1px solid var(--border-color); font-size: 12px; }
.pc__session-row:last-child { border-bottom: none; }
.pc__session-left { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.pc__session-date { color: var(--text-muted); white-space: nowrap; }
.pc__session-dur { font-weight: 600; color: var(--text-color); white-space: nowrap; }
.pc__session-status { font-size: 10px; font-weight: 700; border-radius: 3px; padding: 1px 5px; }
.status--submitted { background: var(--green-50, #f0fdf4); color: var(--green-700, #15803d); }
.status--draft     { background: var(--yellow-50, #fefce8); color: var(--yellow-700, #a16207); }
.pc__session-result { flex: 1; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pc__session-link { color: var(--text-muted); opacity: 0.5; flex-shrink: 0; display: flex; align-items: center; }
.pc__session-link:hover { opacity: 1; }

/* ── Inline panels ─────────────────────────────────────────────── */
.pc__panel { border-top: 1px solid var(--border-color); }
.pc__panel--start { background: var(--green-50, #f0fdf4); border-top-color: var(--green-200, #bbf7d0); }
.pc__panel--stop  { background: var(--red-50, #fef2f2); border-top-color: var(--red-200, #fecaca); }

.pc__panel-inner { padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.pc__panel-row { display: flex; align-items: flex-end; gap: 10px; }
.pc__panel-row--top { align-items: flex-start; }
.pc__panel-field { display: flex; flex-direction: column; gap: 4px; }
.pc__panel-field--full { flex: 1; }
.pc__panel-field--grow { flex: 1; min-width: 0; }
.pc__panel-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); }
.pc__panel-required { color: var(--red-600, #dc2626); }
.pc__panel-input-row { display: flex; align-items: center; gap: 8px; }
.pc__panel-input {
  border: 1px solid var(--border-color); border-radius: 6px;
  background: var(--card-bg); color: var(--text-color);
  font-size: 13.5px; font-family: inherit; padding: 6px 10px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.pc__panel-input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }
.pc__panel-input--sm   { width: 80px; }
.pc__panel-input--full { width: 100%; box-sizing: border-box; }
.pc__panel-unit { font-size: 12.5px; color: var(--text-muted); font-weight: 500; }
.pc__panel-textarea {
  width: 100%; border: 1px solid var(--border-color); border-radius: 6px;
  background: var(--card-bg); color: var(--text-color); font-size: 13px;
  font-family: inherit; padding: 7px 10px; resize: none; box-sizing: border-box;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.pc__panel-textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }
.pc__panel-select {
  border: 1px solid var(--border-color); border-radius: 6px;
  background: var(--card-bg); color: var(--text-color);
  font-size: 13px; font-family: inherit; padding: 6px 10px;
}
.pc__panel-select--full { width: 100%; box-sizing: border-box; }
.pc__panel-actions { display: flex; align-items: center; gap: 6px; }
.pc__panel-actions--end { margin-left: auto; }
.pc__panel-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 6px 13px; border-radius: 6px; font-size: 12.5px; font-weight: 600;
  cursor: pointer; border: 1px solid transparent; line-height: 1;
  transition: background 0.12s, border-color 0.12s;
}
.pc__panel-btn--ghost   { background: none; border-color: var(--border-color); color: var(--text-muted); }
.pc__panel-btn--ghost:hover { background: var(--control-bg); }
.pc__panel-btn--primary { background: var(--primary); color: #fff; border-color: var(--primary); }
.pc__panel-btn--primary:hover { filter: brightness(0.92); }
.pc__panel-btn--danger  { background: var(--red-600, #dc2626); color: #fff; border-color: var(--red-600, #dc2626); }
.pc__panel-btn--danger:hover { filter: brightness(0.9); }

/* ── Transition ────────────────────────────────────────────────── */
.panel-enter-active, .panel-leave-active { transition: max-height 0.2s ease, opacity 0.2s; overflow: hidden; }
.panel-enter-from, .panel-leave-to { max-height: 0; opacity: 0; }
.panel-enter-to, .panel-leave-from { max-height: 400px; opacity: 1; }
</style>

<style>
[data-theme="dark"] .pc--running { box-shadow: 0 0 0 3px rgba(96,165,250,0.12); }
[data-theme="dark"] .pc__panel--start { background: rgba(34,197,94,0.06); border-top-color: rgba(34,197,94,0.2); }
[data-theme="dark"] .pc__panel--stop  { background: rgba(220,38,38,0.06); border-top-color: rgba(220,38,38,0.2); }
</style>
