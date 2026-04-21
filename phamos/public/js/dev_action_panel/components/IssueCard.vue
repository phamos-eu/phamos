<script setup>
import { ref, computed } from "vue";

// GitLab label colors
const LABEL_COLORS = {
  "Hotfix":                 { bg: "#dc143c", text: "#fff" },
  "Revision Needed":        { bg: "#dc143c", text: "#fff" },
  "P:1":                    { bg: "#dc143c", text: "#fff" },
  "Critical":               { bg: "#cd5b45", text: "#fff" },
  "P:2":                    { bg: "#9400d3", text: "#fff" },
  "Discussion":             { bg: "#ed9121", text: "#fff" },
  "P:3":                    { bg: "#6699cc", text: "#fff" },
  "PR Review":              { bg: "#6699cc", text: "#fff" },
  "Merged into Production": { bg: "#6699cc", text: "#fff" },
  "Working":                { bg: "#6699cc", text: "#fff" },
  "Ready for Dev":          { bg: "#eee600", text: "#1a1a1a" },
  "Ready for Staging":      { bg: "#009966", text: "#fff" },
  "Ready for Release":      { bg: "#009966", text: "#fff" },
  "Testing":                { bg: "#009966", text: "#fff" },
  "PM Review":              { bg: "#8fbc8f", text: "#1a1a1a" },
  "Ready for Production":   { bg: "#8fbc8f", text: "#1a1a1a" },
  "Testing on Production":  { bg: "#330066", text: "#fff" },
  "Onboarding Tasks":       { bg: "#808080", text: "#fff" },
  "Open":                   { bg: "#1f1f1f", text: "#fff" },
  "Closed":                 { bg: "#424242", text: "#fff" },
  "Support Task":           { bg: "#616161", text: "#fff" },
};

function labelStyle(name) {
  const c = LABEL_COLORS[name] || { bg: "#6b7280", text: "#fff" };
  return { background: c.bg, color: c.text, borderColor: c.bg };
}

function labelNames(labels) {
  if (!labels) return [];
  return labels.split(",").map(l => l.trim()).filter(Boolean);
}

const props = defineProps({
  issue: Object,
  activeSession: Object,
  elapsedSeconds: Number,
});

const emit = defineEmits(["start", "pause", "resume", "stop"]);

// Panel state
const panel = ref(null); // null | 'start' | 'stop'
const sessionsOpen = ref(false);
const sessions = ref([]);
const loadingSessions = ref(false);

// Start form
const expectedHours = ref(1);
const startGoal = ref("");

// Stop form
const stopResult = ref("");
const stopBillable = ref(100);
const stopActivityType = ref("");
const activityTypes = ["Working Alone", "Working with Customer", "Working With Team"];

// Derived
const isActive = computed(() => props.activeSession?.gitlab_issue === props.issue.name);
const sessionState = computed(() => isActive.value ? props.activeSession?.session_state : null);
const hasAnySession = computed(() => !!props.activeSession);

function fmtElapsed(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
}
function fmtDuration(s) {
  if (!s) return "—";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}
function fmtDate(dt) {
  if (!dt) return "";
  const d = new Date(dt);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

const due = computed(() => {
  if (!props.issue.due_date) return null;
  const today = new Date(); today.setHours(0,0,0,0);
  const d = new Date(props.issue.due_date);
  const diff = Math.round((d - today) / 86400000);
  if (diff < 0)  return { text: `${-diff}d overdue`, cls: "due--overdue" };
  if (diff === 0) return { text: "Due today",        cls: "due--today" };
  if (diff <= 3)  return { text: `Due in ${diff}d`,  cls: "due--soon" };
  return            { text: props.issue.due_date,    cls: "due--ok" };
});

// Actions
function openStart() { panel.value = panel.value === 'start' ? null : 'start'; stopResult.value = ""; }
function openStop() { panel.value = panel.value === 'stop' ? null : 'stop'; }
function closePanel() { panel.value = null; }

function confirmStart() {
  if (!expectedHours.value || expectedHours.value < 0.25) { frappe.msgprint(__("Minimum 0.25h")); return; }
  emit("start", { issue: props.issue, expectedTime: Math.round(parseFloat(expectedHours.value) * 3600), goal: startGoal.value.trim() || null });
  panel.value = null; startGoal.value = "";
}
function confirmStop() {
  if (!stopResult.value.trim()) { frappe.msgprint(__("Please describe what you accomplished.")); return; }
  if (!stopActivityType.value) { frappe.msgprint(__("Please select an Activity Type.")); return; }
  emit("stop", { result: stopResult.value.trim(), percentBillable: stopBillable.value, activityType: stopActivityType.value });
  panel.value = null; stopResult.value = ""; stopActivityType.value = "";
}

async function toggleSessions() {
  sessionsOpen.value = !sessionsOpen.value;
  if (sessionsOpen.value && !sessions.value.length) {
    loadingSessions.value = true;
    const r = await frappe.call({
      method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_issue_timesheets",
      args: { gitlab_issue_name: props.issue.name },
    });
    sessions.value = r.message || [];
    loadingSessions.value = false;
  }
}

function onStartKey(e) { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) confirmStart(); if (e.key === "Escape") closePanel(); }
function onStopKey(e)  { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) confirmStop();  if (e.key === "Escape") closePanel(); }
</script>

<template>
  <div
    class="ic"
    :class="{
      'ic--active': isActive,
      'ic--running': sessionState === 'running',
      'ic--paused': sessionState === 'paused',
      'ic--blocked': hasAnySession && !isActive,
    }"
  >
    <!-- Card body -->
    <div class="ic__body">
      <!-- Status dot -->
      <div class="ic__side">
        <span class="ic__dot" :class="{
          'dot--idle': !hasAnySession,
          'dot--blocked': hasAnySession && !isActive,
          'dot--running': sessionState === 'running',
          'dot--paused': sessionState === 'paused',
        }"></span>
      </div>

      <div class="ic__content">
        <!-- Meta row -->
        <div class="ic__meta">
          <a v-if="issue.issue_url" :href="issue.issue_url" target="_blank" class="ic__id">#{{ issue.issue_id }}</a>
          <span v-else class="ic__id">#{{ issue.issue_id }}</span>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" opacity="0.3"><path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/></svg>
          <span v-if="issue.gitlab_project_title" class="ic__project">{{ issue.gitlab_project_title }}</span>
          <template v-if="issue.parent_issue_title">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" opacity="0.3"><path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/></svg>
            <span class="ic__parent">#{{ issue.parent_issue_id }}</span>
          </template>
          <span class="ic__flex"></span>
          <span v-if="due" class="ic__due" :class="due.cls">{{ due.text }}</span>
        </div>

        <!-- Title + open link -->
        <div class="ic__title-row">
          <a v-if="issue.issue_url" :href="issue.issue_url" target="_blank" class="ic__title" :title="issue.title">{{ issue.title }}</a>
          <span v-else class="ic__title">{{ issue.title }}</span>
          <a v-if="issue.issue_url" :href="issue.issue_url" target="_blank" class="ic__ext-link" title="Open in GitLab">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg>
          </a>
        </div>

        <!-- Info row: assignee · due date · tracked · labels -->
        <div class="ic__info">
          <span v-if="issue.assignee" class="ic__info-item">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" class="ic__info-icon"><path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/></svg>
            {{ issue.assignee }}
          </span>
          <span v-if="issue.due_date" class="ic__info-sep">·</span>
          <span v-if="issue.due_date" class="ic__info-item" :class="due ? due.cls : ''">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="ic__info-icon"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
            {{ fmtDate(issue.due_date) }}
          </span>
          <span v-if="issue.total_tracked_seconds" class="ic__info-sep">·</span>
          <span v-if="issue.total_tracked_seconds" class="ic__info-item ic__info-item--tracked">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="ic__info-icon"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            {{ fmtDuration(issue.total_tracked_seconds) }} tracked
          </span>
          <span
            v-for="lbl in labelNames(issue.labels).slice(0, 3)"
            :key="lbl"
            class="ic__label"
            :style="labelStyle(lbl)"
          >{{ lbl }}</span>
          <span class="ic__info-flex"></span>
          <!-- Action buttons -->
          <span v-if="isActive" class="ic__timer" :class="sessionState === 'running' ? 'timer--green' : 'timer--amber'">
            {{ fmtElapsed(elapsedSeconds) }}
          </span>
          <button v-if="!hasAnySession" class="ic__btn ic__btn--start" :class="{ 'ic__btn--open': panel === 'start' }" @click="openStart">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
            Start
          </button>
          <template v-else-if="isActive">
            <button v-if="sessionState === 'running'" class="ic__btn ic__btn--pause" @click="emit('pause')">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
              Pause
            </button>
            <button v-else class="ic__btn ic__btn--resume" @click="emit('resume')">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
              Resume
            </button>
            <button class="ic__btn ic__btn--stop" :class="{ 'ic__btn--open': panel === 'stop' }" @click="openStop">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h12v12H6z"/></svg>
              Stop
            </button>
          </template>
          <button v-else class="ic__btn ic__btn--muted" disabled>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
            Start
          </button>
        </div>
      </div>
    </div>

    <!-- ── Inline Start panel ───────────────────────────────────── -->
    <Transition name="panel">
      <div v-if="panel === 'start'" class="ic__panel ic__panel--start" @keydown="onStartKey">
        <div class="ic__panel-inner">
          <div class="ic__panel-field">
            <label class="ic__panel-label">Expected time</label>
            <div class="ic__panel-input-row">
              <input
                v-model.number="expectedHours"
                type="number" min="0.25" step="0.25"
                class="ic__panel-input ic__panel-input--sm"
                autofocus
              />
              <span class="ic__panel-unit">hours</span>
              <span v-if="expectedHours" class="ic__panel-hint">
                = {{ Math.floor(expectedHours) }}h {{ Math.round((expectedHours % 1) * 60) }}m
              </span>
            </div>
          </div>
          <div class="ic__panel-field ic__panel-field--full">
            <label class="ic__panel-label">Goal</label>
            <textarea
              v-model="startGoal"
              class="ic__panel-textarea"
              rows="2"
              :placeholder="issue.title"
            ></textarea>
          </div>
          <div class="ic__panel-actions">
            <button class="ic__panel-btn ic__panel-btn--ghost" @click="closePanel">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
              Cancel
            </button>
            <button class="ic__panel-btn ic__panel-btn--primary" @click="confirmStart">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
              Begin
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- ── Inline Stop panel ────────────────────────────────────── -->
    <Transition name="panel">
      <div v-if="panel === 'stop'" class="ic__panel ic__panel--stop" @keydown="onStopKey">
        <div class="ic__panel-inner">
          <div class="ic__panel-field ic__panel-field--full">
            <label class="ic__panel-label">What did you accomplish?</label>
            <textarea
              v-model="stopResult"
              class="ic__panel-textarea"
              rows="2"
              placeholder="Completed the feature, fixed the bug, wrote tests…"
              autofocus
            ></textarea>
          </div>
          <div class="ic__panel-row">
            <div class="ic__panel-field">
              <label class="ic__panel-label">Activity Type <span class="ic__panel-required">*</span></label>
              <select v-model="stopActivityType" class="ic__panel-select ic__panel-select--full">
                <option value="">— Select —</option>
                <option v-for="at in activityTypes" :key="at" :value="at">{{ at }}</option>
              </select>
            </div>
            <div class="ic__panel-field">
              <label class="ic__panel-label">Billable %</label>
              <select v-model.number="stopBillable" class="ic__panel-select">
                <option :value="100">100%</option>
                <option :value="75">75%</option>
                <option :value="50">50%</option>
                <option :value="25">25%</option>
                <option :value="0">0% — Internal</option>
              </select>
            </div>
            <div class="ic__panel-actions ic__panel-actions--end">
              <button class="ic__panel-btn ic__panel-btn--ghost" @click="closePanel">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
                Cancel
              </button>
              <button class="ic__panel-btn ic__panel-btn--danger" @click="confirmStop">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
                Complete
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- ── Sessions section ─────────────────────────────────────── -->
    <div v-if="issue.timesheet_count > 0" class="ic__sessions">
      <button class="ic__sessions-toggle" @click="toggleSessions">
        <svg class="ic__sessions-chevron" :class="{ 'rotated': sessionsOpen }" width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M7 10l5 5 5-5z"/></svg>
        {{ issue.timesheet_count }} {{ issue.timesheet_count === 1 ? 'session' : 'sessions' }}
        <span class="ic__sessions-badge">tracked</span>
      </button>

      <Transition name="panel">
        <div v-if="sessionsOpen" class="ic__sessions-list">
          <div v-if="loadingSessions" class="ic__sessions-loading">Loading…</div>
          <div v-else-if="!sessions.length" class="ic__sessions-loading">No records found.</div>
          <div v-for="s in sessions" :key="s.name" class="ic__session-row">
            <div class="ic__session-left">
              <span class="ic__session-date">{{ fmtDate(s.from_time) }}</span>
              <span class="ic__session-dur">{{ fmtDuration(s.actual_time) }}</span>
              <span class="ic__session-status" :class="s.docstatus === 1 ? 'status--submitted' : 'status--draft'">
                {{ s.docstatus === 1 ? 'Submitted' : 'Draft' }}
              </span>
            </div>
            <div class="ic__session-result">{{ s.result || s.goal || '—' }}</div>
            <a :href="`/app/timesheet-record/${s.name}`" target="_blank" class="ic__session-link" title="Open record">
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
.ic {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  overflow: hidden;
  transition: box-shadow 0.15s, border-color 0.15s;
}
.ic:hover { box-shadow: 0 1px 6px rgba(0,0,0,0.07); border-color: var(--gray-300, #d1d5db); }
.ic--active { border-color: var(--primary); }
.ic--running { box-shadow: 0 0 0 3px rgba(37,99,235,0.08); }
.ic--blocked { opacity: 0.72; }

/* ── Body ──────────────────────────────────────────────────────── */
.ic__body { display: flex; }

.ic__side {
  display: flex; align-items: flex-start;
  padding: 14px 0 14px 13px; flex-shrink: 0;
}
.ic--running .ic__side { border-left: 3px solid var(--green-500, #22c55e); padding-left: 10px; }
.ic--paused  .ic__side { border-left: 3px solid var(--yellow-500, #eab308); padding-left: 10px; }

.ic__dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 2px; flex-shrink: 0; transition: background 0.2s; }
.dot--idle    { background: var(--gray-300, #d1d5db); }
.dot--blocked { background: var(--gray-200, #e5e7eb); }
.dot--running { background: var(--green-500, #22c55e); box-shadow: 0 0 0 3px rgba(34,197,94,0.2); animation: pulse 2s ease-in-out infinite; }
.dot--paused  { background: var(--yellow-500, #eab308); }
@keyframes pulse { 0%,100% { box-shadow: 0 0 0 3px rgba(34,197,94,0.2); } 50% { box-shadow: 0 0 0 5px rgba(34,197,94,0.06); } }

.ic__content { flex: 1; min-width: 0; padding: 10px 13px 10px 8px; display: flex; flex-direction: column; gap: 4px; }

/* ── Meta ──────────────────────────────────────────────────────── */
.ic__meta { display: flex; align-items: center; gap: 3px; font-size: 12px; color: var(--text-muted); overflow: hidden; }
.ic__id { font-family: var(--font-monospace, monospace); font-size: 11px; font-weight: 700; color: var(--primary); text-decoration: none; background: var(--blue-50, #eff6ff); border-radius: 3px; padding: 1px 5px; flex-shrink: 0; }
.ic__id:hover { text-decoration: underline; }
.ic__project { font-weight: 500; font-size: 11.5px; white-space: nowrap; }
.ic__parent { font-size: 11.5px; white-space: nowrap; }
.ic__flex { flex: 1; }
.ic__due { font-size: 11px; font-weight: 600; border-radius: 4px; padding: 1.5px 6px; white-space: nowrap; flex-shrink: 0; }
.due--overdue { background: var(--red-50, #fef2f2); color: var(--red-600, #dc2626); }
.due--today   { background: var(--orange-50, #fff7ed); color: var(--orange-600, #ea580c); }
.due--soon    { background: var(--yellow-50, #fefce8); color: var(--yellow-700, #a16207); }
.due--ok      { background: var(--control-bg, #f3f4f6); color: var(--text-muted); }

/* ── Title ─────────────────────────────────────────────────────── */
.ic__title-row { display: flex; align-items: flex-start; gap: 6px; }
.ic__title { flex: 1; font-size: 13.5px; font-weight: 500; color: var(--text-color); text-decoration: none; line-height: 1.4; letter-spacing: -0.01em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ic__title:hover { color: var(--primary); text-decoration: underline; }
.ic__ext-link { color: var(--text-muted); flex-shrink: 0; display: flex; align-items: center; opacity: 0.5; transition: opacity 0.1s; margin-top: 2px; }
.ic__ext-link:hover { opacity: 1; }

/* ── Info row ──────────────────────────────────────────────────── */
.ic__info {
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
  margin-top: 5px; font-size: 11.5px; color: var(--text-muted);
}
.ic__info-item {
  display: inline-flex; align-items: center; gap: 4px; white-space: nowrap;
}
.ic__info-icon { flex-shrink: 0; opacity: 0.7; }
.ic__info-sep { color: var(--border-color); font-size: 13px; line-height: 1; }
.ic__info-item--tracked { color: #16a34a; font-weight: 600; }
.ic__info-item.due--overdue { color: var(--red-600, #dc2626); background: var(--red-50, #fef2f2); padding: 2px 7px; border-radius: 4px; }
.ic__info-item.due--today   { color: var(--orange-600, #ea580c); background: var(--orange-50, #fff7ed); padding: 2px 7px; border-radius: 4px; }
.ic__info-item.due--soon    { color: var(--yellow-700, #a16207); background: var(--yellow-50, #fefce8); padding: 2px 7px; border-radius: 4px; }
.ic__info-item.due--ok      { color: var(--text-muted); background: var(--control-bg); padding: 2px 7px; border-radius: 4px; }
.ic__label {
  font-size: 10.5px; font-weight: 700; padding: 2px 7px; border-radius: 10px;
  border: 1px solid transparent; white-space: nowrap; letter-spacing: 0.01em;
}
.ic__info-flex { flex: 1; min-width: 4px; }
.ic__actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.ic__timer { font-family: var(--font-monospace, monospace); font-size: 12px; font-weight: 700; letter-spacing: 0.04em; white-space: nowrap; flex-shrink: 0; }
.timer--green { color: var(--green-600, #16a34a); }
.timer--amber { color: var(--yellow-600, #ca8a04); }

/* ── Buttons ───────────────────────────────────────────────────── */
.ic__btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 11px; border-radius: 6px; font-size: 12px; font-weight: 600;
  cursor: pointer; border: 1px solid transparent;
  transition: background 0.12s, border-color 0.12s, box-shadow 0.12s;
  white-space: nowrap; line-height: 1;
}
.ic__btn--start  { background: #15803d; color: #fff; border-color: #15803d; }
.ic__btn--start:hover, .ic__btn--start.ic__btn--open { background: #166534; border-color: #166534; }
.ic__btn--pause  { background: var(--yellow-50, #fefce8); color: var(--yellow-700, #a16207); border-color: var(--yellow-200, #fef08a); }
.ic__btn--pause:hover { background: var(--yellow-100, #fef9c3); }
.ic__btn--resume { background: var(--green-50, #f0fdf4); color: var(--green-700, #15803d); border-color: var(--green-200, #bbf7d0); }
.ic__btn--resume:hover { background: var(--green-100, #dcfce7); }
.ic__btn--stop   { background: var(--red-50, #fef2f2); color: var(--red-600, #dc2626); border-color: var(--red-200, #fecaca); }
.ic__btn--stop:hover, .ic__btn--stop.ic__btn--open { background: var(--red-100, #fee2e2); border-color: var(--red-400, #f87171); }
.ic__btn--muted  { background: var(--control-bg); color: var(--text-muted); border-color: var(--border-color); cursor: not-allowed; opacity: 0.55; }

/* ── Inline panels ─────────────────────────────────────────────── */
.ic__panel {
  border-top: 1px solid var(--border-color);
  background: var(--bg-color);
}
.ic__panel--start { background: var(--green-50, #f0fdf4); border-top-color: var(--green-200, #bbf7d0); }
.ic__panel--stop  { background: var(--red-50, #fef2f2); border-top-color: var(--red-200, #fecaca); }

.ic__panel-inner { padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.ic__panel-field { display: flex; flex-direction: column; gap: 4px; }
.ic__panel-field--full { flex: 1; }
.ic__panel-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); }
.ic__panel-input-row { display: flex; align-items: center; gap: 8px; }
.ic__panel-input {
  border: 1px solid var(--border-color); border-radius: 6px;
  background: var(--card-bg); color: var(--text-color);
  font-size: 13.5px; font-family: inherit; padding: 6px 10px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.ic__panel-input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }
.ic__panel-input--sm { width: 80px; }
.ic__panel-input--full { width: 100%; box-sizing: border-box; }
.ic__panel-unit { font-size: 12.5px; color: var(--text-muted); font-weight: 500; }
.ic__panel-hint { font-size: 12px; color: var(--text-muted); }
.ic__panel-optional { font-size: 10px; font-weight: 400; color: var(--text-muted); text-transform: none; letter-spacing: 0; }
.ic__panel-required { color: var(--red-600, #dc2626); }

.ic__panel-textarea {
  width: 100%; border: 1px solid var(--border-color); border-radius: 6px;
  background: var(--card-bg); color: var(--text-color); font-size: 13px;
  font-family: inherit; padding: 7px 10px; resize: none; box-sizing: border-box;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.ic__panel-textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }

.ic__panel-select {
  border: 1px solid var(--border-color); border-radius: 6px;
  background: var(--card-bg); color: var(--text-color);
  font-size: 13px; font-family: inherit; padding: 6px 10px;
}
.ic__panel-select--full { width: 100%; box-sizing: border-box; }

.ic__panel-row { display: flex; align-items: flex-end; gap: 10px; }
.ic__panel-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.ic__panel-actions--end { margin-left: auto; }

.ic__panel-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 6px 13px; border-radius: 6px; font-size: 12.5px; font-weight: 600;
  cursor: pointer; border: 1px solid transparent; line-height: 1;
  transition: background 0.12s, border-color 0.12s;
}
.ic__panel-btn--ghost  { background: none; border-color: var(--border-color); color: var(--text-muted); }
.ic__panel-btn--ghost:hover { background: var(--control-bg); color: var(--text-color); }
.ic__panel-btn--primary { background: #15803d; color: #fff; border-color: #15803d; }
.ic__panel-btn--primary:hover { background: #166534; border-color: #166534; }
.ic__panel-btn--danger  { background: var(--red-600, #dc2626); color: #fff; border-color: var(--red-600, #dc2626); }
.ic__panel-btn--danger:hover { background: var(--red-700, #b91c1c); }

/* ── Sessions ──────────────────────────────────────────────────── */
.ic__sessions { border-top: 1px solid var(--border-color); }

.ic__sessions-toggle {
  display: flex; align-items: center; gap: 6px;
  width: 100%; padding: 7px 13px;
  background: none; border: none; cursor: pointer;
  font-size: 12px; color: var(--text-muted);
  transition: background 0.1s, color 0.1s; text-align: left;
}
.ic__sessions-toggle:hover { background: var(--control-bg); color: var(--text-color); }
.ic__sessions-chevron { transition: transform 0.2s; flex-shrink: 0; }
.ic__sessions-chevron.rotated { transform: rotate(180deg); }
.ic__sessions-badge { font-size: 10.5px; font-weight: 600; background: var(--control-bg); border-radius: 10px; padding: 1px 6px; }

.ic__sessions-list { border-top: 1px solid var(--border-color); }
.ic__sessions-loading { padding: 10px 14px; font-size: 12px; color: var(--text-muted); font-style: italic; }
.ic__session-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 14px; border-bottom: 1px solid var(--border-color); font-size: 12px;
}
.ic__session-row:last-child { border-bottom: none; }
.ic__session-left { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.ic__session-date { color: var(--text-muted); white-space: nowrap; }
.ic__session-dur { font-weight: 700; color: var(--text-color); white-space: nowrap; }
.ic__session-status { font-size: 10.5px; font-weight: 600; border-radius: 4px; padding: 1px 6px; white-space: nowrap; }
.status--submitted { background: var(--green-50, #f0fdf4); color: var(--green-600, #16a34a); }
.status--draft     { background: var(--yellow-50, #fefce8); color: var(--yellow-700, #a16207); }
.ic__session-result { flex: 1; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11.5px; }
.ic__session-link { color: var(--text-muted); display: flex; align-items: center; flex-shrink: 0; opacity: 0.5; transition: opacity 0.1s; }
.ic__session-link:hover { opacity: 1; }

/* ── Transitions ───────────────────────────────────────────────── */
.panel-enter-active { transition: max-height 0.22s ease-out, opacity 0.18s ease-out; max-height: 300px; overflow: hidden; }
.panel-leave-active { transition: max-height 0.18s ease-in, opacity 0.15s ease-in; overflow: hidden; }
.panel-enter-from   { max-height: 0; opacity: 0; }
.panel-leave-to     { max-height: 0; opacity: 0; }
.panel-enter-to     { max-height: 300px; opacity: 1; }
</style>

<style>
/* ── Dark mode overrides ───────────────────────────────────────── */
[data-theme="dark"] .ic__id {
  background: rgba(255,255,255,0.1);
  color: #93c5fd;
}
[data-theme="dark"] .due--overdue {
  background: rgba(220,38,38,0.2); color: #fca5a5;
}
[data-theme="dark"] .due--today {
  background: rgba(234,88,12,0.2); color: #fdba74;
}
[data-theme="dark"] .due--soon {
  background: rgba(234,179,8,0.18); color: #fde68a;
}
[data-theme="dark"] .ic__info-item.due--overdue { color: #fca5a5; background: rgba(220,38,38,0.2); }
[data-theme="dark"] .ic__info-item.due--today   { color: #fdba74; background: rgba(234,88,12,0.2); }
[data-theme="dark"] .ic__info-item.due--soon    { color: #fde68a; background: rgba(234,179,8,0.18); }
[data-theme="dark"] .ic__info-item.due--ok      { color: var(--text-muted); background: var(--control-bg); }
[data-theme="dark"] .ic__btn--pause {
  background: rgba(234,179,8,0.15); color: #fde68a; border-color: rgba(234,179,8,0.35);
}
[data-theme="dark"] .ic__btn--pause:hover {
  background: rgba(234,179,8,0.25);
}
[data-theme="dark"] .ic__btn--resume {
  background: rgba(21,128,61,0.15); color: #86efac; border-color: rgba(21,128,61,0.35);
}
[data-theme="dark"] .ic__btn--resume:hover {
  background: rgba(21,128,61,0.25);
}
[data-theme="dark"] .ic__btn--stop {
  background: rgba(220,38,38,0.15); color: #fca5a5; border-color: rgba(220,38,38,0.35);
}
[data-theme="dark"] .ic__btn--stop:hover,
[data-theme="dark"] .ic__btn--stop.ic__btn--open {
  background: rgba(220,38,38,0.25); border-color: rgba(220,38,38,0.55);
}
[data-theme="dark"] .ic__panel--start {
  background: rgba(21,128,61,0.1); border-top-color: rgba(21,128,61,0.3);
}
[data-theme="dark"] .ic__panel--stop {
  background: rgba(220,38,38,0.1); border-top-color: rgba(220,38,38,0.3);
}
[data-theme="dark"] .ic__panel-btn--danger {
  background: #b91c1c; border-color: #b91c1c;
}
[data-theme="dark"] .ic__panel-btn--danger:hover {
  background: #991b1b; border-color: #991b1b;
}
</style>
