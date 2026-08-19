<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import Sidebar from "./components/Sidebar.vue";
import StatsBar from "./components/StatsBar.vue";
import FilterBar from "./components/FilterBar.vue";
import IssueList from "./components/IssueList.vue";
import BreakModal from "./components/BreakModal.vue";
import BreakConfirm from "./components/BreakConfirm.vue";
import CalendarView from "./components/CalendarView.vue";
import TimesheetList from "./components/TimesheetList.vue";
import ProjectsView from "./components/ProjectsView.vue";

const issues = ref([]);
const stats = ref(null);
const loading = ref(false);
const syncing = ref(false);
const showBreakConfirm = ref(false);
const showBreakModal = ref(false);
const breakFrom = ref(null); // system-tz string set when timer is paused
const activeSession = ref(null);
const elapsedSeconds = ref(0);
const sidebarOpen = ref(true);
const selectedProject = ref(null);
const currentView = ref("issues"); // 'issues' | 'timesheets' | 'team' | 'projects'
const mineOnly = ref(true); // default: show only current user's issues

// Projects section
const myProjects = ref([]);
const allProjects = ref([]);
const projectsFilter = ref("my"); // 'my' | 'all'
const projectsLoading = ref(false);
const activeProjectSession = ref(null);
const projectElapsedSeconds = ref(0);
let projectTimerInterval = null;

// Filter state
const searchQuery = ref("");
const dueFilter = ref("all");
const assigneeFilter = ref([]);
const labelFilter = ref([]);
const sortBy = ref("due_date");
const sortDir = ref("asc");
function clearAllFilters() { searchQuery.value = ""; dueFilter.value = "all"; assigneeFilter.value = []; labelFilter.value = []; sortBy.value = "due_date"; sortDir.value = "asc"; }

// Dynamic filter options derived from the loaded issues
const assigneeOptions = computed(() => {
  const set = new Set();
  issues.value.forEach(i => { if (i.assignee) set.add(i.assignee); });
  return [...set].sort();
});
const labelOptions = computed(() => {
  const set = new Set();
  issues.value.forEach(i => {
    if (i.labels) i.labels.split(",").map(l => l.trim()).filter(Boolean).forEach(l => set.add(l));
  });
  return [...set].sort();
});

// Derived
const myIssuesCount = computed(() => issues.value.filter(i => i.is_mine).length);

const projects = computed(() => {
  const base = mineOnly.value ? issues.value.filter(i => i.is_mine) : issues.value;
  const map = {};
  base.forEach(i => {
    if (i.gitlab_project) {
      if (!map[i.gitlab_project]) map[i.gitlab_project] = { name: i.gitlab_project, title: i.gitlab_project_title || i.gitlab_project, count: 0 };
      map[i.gitlab_project].count++;
    }
  });
  return Object.values(map).sort((a, b) => a.title.localeCompare(b.title));
});

const filteredIssues = computed(() => {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const weekEnd = new Date(today); weekEnd.setDate(today.getDate() + 7);
  const activeIssueName = activeSession.value?.gitlab_issue;
  const activeIssue = issues.value.find(i => i.name === activeIssueName);
  let list = issues.value.filter(i => i.name !== activeIssueName);

  if (mineOnly.value) list = list.filter(i => i.is_mine);
  if (selectedProject.value) list = list.filter(i => i.gitlab_project === selectedProject.value);

  const q = searchQuery.value.trim().toLowerCase();
  if (q) list = list.filter(i =>
    i.title?.toLowerCase().includes(q) ||
    String(i.issue_id).includes(q) ||
    i.gitlab_project_title?.toLowerCase().includes(q) ||
    i.assignee?.toLowerCase().includes(q) ||
    i.labels?.toLowerCase().includes(q)
  );

  if (assigneeFilter.value.length) list = list.filter(i => assigneeFilter.value.includes(i.assignee));
  if (labelFilter.value.length) list = list.filter(i =>
    i.labels && labelFilter.value.some(l => i.labels.split(",").map(s => s.trim()).includes(l))
  );

  if (dueFilter.value !== "all") {
    list = list.filter(i => {
      if (dueFilter.value === "no_due") return !i.due_date;
      if (!i.due_date) return false;
      const d = new Date(i.due_date);
      if (dueFilter.value === "overdue")   return d < today;
      if (dueFilter.value === "today")     return d.getTime() === today.getTime();
      if (dueFilter.value === "this_week") return d >= today && d <= weekEnd;
      return true;
    });
  }

  list = [...list].sort((a, b) => {
    let va, vb;
    if (sortBy.value === "due_date") {
      if (!a.due_date && !b.due_date) return 0;
      if (!a.due_date) return 1;
      if (!b.due_date) return -1;
      va = new Date(a.due_date).getTime(); vb = new Date(b.due_date).getTime();
    } else if (sortBy.value === "id") {
      va = parseInt(a.issue_id) || 0; vb = parseInt(b.issue_id) || 0;
    } else if (sortBy.value === "project") {
      va = (a.gitlab_project_title || "").toLowerCase(); vb = (b.gitlab_project_title || "").toLowerCase();
    } else if (sortBy.value === "title") {
      va = (a.title || "").toLowerCase(); vb = (b.title || "").toLowerCase();
    } else if (sortBy.value === "priority") {
        const getPriority = (labels) => {
          if (!labels) return 999;

          if (labels.includes("P:1")) return 1;
          if (labels.includes("P:2")) return 2;
          if (labels.includes("P:3")) return 3;

          return 999;
        };

        va = getPriority(a.labels);
        vb = getPriority(b.labels);
      }
    if (va < vb) return sortDir.value === "asc" ? -1 : 1;
    if (va > vb) return sortDir.value === "asc" ? 1 : -1;
    return 0;
  });

  // Re-inject the active issue at the top, bypassing all filters
  if (activeIssue) list = [activeIssue, ...list];
  return list;
});

// Timer
let timerInterval = null;
function startTick() { clearInterval(timerInterval); timerInterval = setInterval(() => { if (activeSession.value?.session_state === "running") elapsedSeconds.value++; }, 1000); }
function stopTick() { clearInterval(timerInterval); timerInterval = null; }

// Labels map: { labelName: { bg: "#hex", text: "#hex" } }
const labelsMap = ref({});

// API
async function loadIssues() { loading.value = true; const r = await frappe.call({ method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_my_issues" }); issues.value = r.message || []; loading.value = false; }
async function loadLabels() {
  const r = await frappe.call({ method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_gitlab_labels" });
  const map = {};
  for (const l of (r.message || [])) {
    map[l.name] = { bg: l.color || "#6b7280", text: l.text_color || "#fff" };
  }
  labelsMap.value = map;
}
async function loadSession() {
  const r = await frappe.call({ method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_active_session" });
  activeSession.value = r.message || null;
  if (activeSession.value) {
    elapsedSeconds.value = activeSession.value.elapsed_seconds || 0;
    if (activeSession.value.session_state === "running") startTick();
    if (activeSession.value.session_state === "paused") breakFrom.value = activeSession.value.break_from || null;
  }
}
async function loadStats() { const r = await frappe.call({ method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_time_stats" }); stats.value = r.message || null; }

// Projects
async function loadMyProjects() {
  const r = await frappe.call({ method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_dev_my_projects" });
  myProjects.value = r.message || [];
}
async function loadAllProjects() {
  const r = await frappe.call({ method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_dev_all_projects" });
  allProjects.value = r.message || [];
}
async function loadActiveProjectSession() {
  const r = await frappe.call({ method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_active_project_session" });
  activeProjectSession.value = r.message || null;
  if (activeProjectSession.value) {
    projectElapsedSeconds.value = activeProjectSession.value.elapsed_seconds || 0;
    if (activeProjectSession.value.session_state === "running") startProjectTick();
  }
}

function startProjectTick() {
  clearInterval(projectTimerInterval);
  projectTimerInterval = setInterval(() => {
    if (activeProjectSession.value?.session_state === "running") projectElapsedSeconds.value++;
  }, 1000);
}
function stopProjectTick() { clearInterval(projectTimerInterval); projectTimerInterval = null; }

async function onStartProjectTimer({ project, expectedTime, goal }) {
  const r = await frappe.call({
    method: "phamos.phamos.page.dev_action_panel.dev_action_panel.start_project_timer",
    args: { project_name: project.name, expected_time: expectedTime, goal },
  });
  if (r.message) {
    activeProjectSession.value = { ...r.message };
    projectElapsedSeconds.value = Math.max(0, r.message.elapsed_seconds || 0);
    startProjectTick();
  }
}

async function onPauseProjectTimer() {
  if (!activeProjectSession.value) return;
  const r = await frappe.call({ method: "phamos.phamos.page.dev_action_panel.dev_action_panel.pause_timer", args: { name: activeProjectSession.value.name } });
  activeProjectSession.value = { ...activeProjectSession.value, session_state: "paused" };
  stopProjectTick();
}

async function onResumeProjectTimer() {
  if (!activeProjectSession.value) return;
  await frappe.call({ method: "phamos.phamos.page.dev_action_panel.dev_action_panel.resume_timer", args: { name: activeProjectSession.value.name } });
  activeProjectSession.value = { ...activeProjectSession.value, session_state: "running" };
  startProjectTick();
}

async function onStopProjectTimer({ result, percentBillable, activityType }) {
  if (!activeProjectSession.value) return;
  const r = await frappe.call({
    method: "phamos.phamos.page.dev_action_panel.dev_action_panel.stop_timer",
    args: { name: activeProjectSession.value.name, result, percent_billable: percentBillable, activity_type: activityType },
  });
  if (r.message) {
    stopProjectTick();
    activeProjectSession.value = null;
    projectElapsedSeconds.value = 0;
    await Promise.all([loadMyProjects(), loadStats()]);
    frappe.show_alert({ message: __("Project session submitted."), indicator: "green" });
  }
}

async function assignProject(project) {
  await frappe.call({
    method: "phamos.phamos.page.dev_action_panel.dev_action_panel.assign_dev_project",
    args: { project_name: project.name },
  });
  frappe.show_alert({ message: __("Project assigned to you."), indicator: "green" });
  await Promise.all([loadMyProjects(), loadAllProjects()]);
}

// Inline start (emitted from card with { issue, expectedTime, goal, manualStartTime? })
async function onStart({ issue, expectedTime, goal, manualStartTime }) {
  const args = { gitlab_issue_name: issue.name, expected_time: expectedTime, goal: goal || null };
  if (manualStartTime) args.manual_start_time = manualStartTime;
  const r = await frappe.call({
    method: "phamos.phamos.page.dev_action_panel.dev_action_panel.start_issue_timer",
    args,
  });
  if (r.message) {
    activeSession.value = { ...r.message, gitlab_issue: issue.name };
    elapsedSeconds.value = Math.max(0, r.message.elapsed_seconds || 0);
    startTick();
    await loadIssues();
  }
}

async function onPause() {
  if (!activeSession.value) return;
  const r = await frappe.call({ method: "phamos.phamos.page.dev_action_panel.dev_action_panel.pause_timer", args: { name: activeSession.value.name } });
  breakFrom.value = r.message?.break_from || null;
  activeSession.value = { ...activeSession.value, session_state: "paused" };
  stopTick();
  await loadIssues();
}

async function onResume() {
  if (!activeSession.value) return;
  if (breakFrom.value) {
    showBreakConfirm.value = true;
  } else {
    await doResume();
  }
}

function onBreakConfirmYes() {
  showBreakConfirm.value = false;
  showBreakModal.value = true;
}

async function onBreakConfirmNo() {
  showBreakConfirm.value = false;
  breakFrom.value = null;
  await doResume();
}

function onBreakConfirmClose() {
  // Dismissed without choosing — session stays paused, no rows written
  showBreakConfirm.value = false;
}

function onBreakModalClose() {
  // Dismissed without choosing — session stays paused, no rows written
  showBreakModal.value = false;
}

async function doResume() {
  await frappe.call({ method: "phamos.phamos.page.dev_action_panel.dev_action_panel.resume_timer", args: { name: activeSession.value.name } });
  activeSession.value = { ...activeSession.value, session_state: "running" };
  startTick();
  await loadIssues();
}

async function onBreakSubmit({ project, activityType, goal, result, percentBillable }) {
  showBreakModal.value = false;
  await frappe.call({
    method: "phamos.phamos.page.dev_action_panel.dev_action_panel.create_break_timesheet",
    args: {
      from_time: breakFrom.value,
      project,
      goal,
      result,
      percent_billable: percentBillable,
      activity_type: activityType || null,
    },
  });
  breakFrom.value = null;
  await doResume();
  frappe.show_alert({ message: __("Break timesheet submitted."), indicator: "green" });
}

async function onBreakSkip() {
  showBreakModal.value = false;
  breakFrom.value = null;
  await doResume();
}

// Inline stop (emitted from card with { result, percentBillable, activityType, manualEndTime? })
async function onStop({ result, percentBillable, activityType, manualEndTime }) {
  const args = { name: activeSession.value.name, result, percent_billable: percentBillable, activity_type: activityType };
  if (manualEndTime) args.manual_end_time = manualEndTime;
  const r = await frappe.call({
    method: "phamos.phamos.page.dev_action_panel.dev_action_panel.stop_timer",
    args,
  });
  if (r.message) { stopTick(); activeSession.value = null; elapsedSeconds.value = 0; await Promise.all([loadIssues(), loadStats()]); frappe.show_alert({ message: __("Session submitted."), indicator: "green" }); }
}

async function onSync() {
  syncing.value = true;
  await Promise.all([loadIssues(), loadStats()]);
  syncing.value = false;
}

onMounted(async () => { await Promise.all([loadIssues(), loadSession(), loadStats(), loadLabels(), loadMyProjects(), loadAllProjects(), loadActiveProjectSession()]); });
onUnmounted(() => { stopTick(); stopProjectTick(); });
</script>

<template>
  <BreakConfirm
    v-if="showBreakConfirm && breakFrom"
    :break-from="breakFrom"
    @confirm="onBreakConfirmYes"
    @skip="onBreakConfirmNo"
    @close="onBreakConfirmClose"
  />
  <BreakModal
    v-if="showBreakModal && breakFrom"
    :break-from="breakFrom"
    @confirm="onBreakSubmit"
    @skip="onBreakSkip"
    @close="onBreakModalClose"
  />

  <div class="dc-root">
    <!-- Top bar: hamburger + title -->
    <div class="dc-topbar">
      <button class="dc-menu-btn" @click="sidebarOpen = !sidebarOpen" :title="sidebarOpen ? 'Collapse' : 'Expand'">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/></svg>
      </button>
      <span class="dc-topbar-title">Developer Action Panel</span>
    </div>

    <!-- Stats cards row -->
    <StatsBar :stats="stats" />

    <!-- Body: sidebar + main -->
    <div class="dc-split">
      <aside class="dc-sidebar" :class="{ 'dc-sidebar--hidden': !sidebarOpen }">
        <Sidebar
          :projects="projects"
          :selected-project="selectedProject"
          :active-session="activeSession"
          :elapsed-seconds="elapsedSeconds"
          :current-view="currentView"
          :total-issues="issues.length"
          :my-issues-count="myIssuesCount"
          :mine-only="mineOnly"
          :syncing="syncing"
          :projects-filter="projectsFilter"
          :my-projects-count="myProjects.length"
          :all-projects-count="allProjects.length"
          :active-project-session="activeProjectSession"
          :project-elapsed-seconds="projectElapsedSeconds"
          @select-project="selectedProject = $event"
          @change-view="currentView = $event"
          @toggle-mine="mineOnly = $event"
          @sync="onSync"
          @navigate-projects="(tab) => { currentView = 'projects'; projectsFilter = tab; }"
        />
      </aside>

      <div class="dc-body">
        <template v-if="currentView === 'issues'">
          <FilterBar
            v-model:search="searchQuery"
            v-model:dueFilter="dueFilter"
            v-model:assigneeFilter="assigneeFilter"
            v-model:labelFilter="labelFilter"
            v-model:sortBy="sortBy"
            v-model:sortDir="sortDir"
            :assignee-options="assigneeOptions"
            :label-options="labelOptions"
            :result-count="filteredIssues.length"
            :total-count="issues.length"
            @clear-all="clearAllFilters"
          />
          <div v-if="loading" class="dc-loading">
            <div class="dc-loading__spinner"></div>
            <span>Loading your issues…</span>
          </div>
          <IssueList
            v-else
            :issues="filteredIssues"
            :all-count="issues.length"
            :active-session="activeSession"
            :elapsed-seconds="elapsedSeconds"
            :selected-project="selectedProject"
            :labels-map="labelsMap"
            :active-project-session="activeProjectSession"
            @start="onStart"
            @pause="onPause"
            @resume="onResume"
            @stop="onStop"
          />
        </template>

        <CalendarView v-else-if="currentView === 'team'" />
        <TimesheetList v-else-if="currentView === 'timesheets'" />
        <ProjectsView
          v-else-if="currentView === 'projects'"
          :filter="projectsFilter"
          :my-projects="myProjects"
          :all-projects="allProjects"
          :active-project-session="activeProjectSession"
          :project-elapsed-seconds="projectElapsedSeconds"
          :loading="projectsLoading"
          :active-issue-session="activeSession"
          @change-filter="projectsFilter = $event"
          @start="onStartProjectTimer"
          @pause="onPauseProjectTimer"
          @resume="onResumeProjectTimer"
          @stop="onStopProjectTimer"
          @assign="assignProject"
        />
      </div>
    </div>
  </div>
</template>

<style>
.layout-main-section { padding: 0 !important; overflow: hidden; }
</style>

<style scoped>
.dc-root {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: calc(100vh - 108px);
  background: var(--bg-color);
}

/* Topbar */
.dc-topbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  height: 40px;
  border-bottom: 1px solid var(--border-color);
  background: var(--card-bg);
  flex-shrink: 0;
}
.dc-menu-btn {
  display: flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border: none; background: transparent;
  border-radius: 6px; color: var(--text-muted); cursor: pointer;
  flex-shrink: 0; transition: background 0.12s, color 0.12s;
}
.dc-menu-btn:hover { background: var(--control-bg); color: var(--text-color); }
.dc-topbar-title {
  font-size: 13px; font-weight: 600; color: var(--text-muted);
  letter-spacing: -0.01em;
}

/* Split */
.dc-split { display: flex; flex: 1; overflow: hidden; min-height: 0; }

/* Sidebar */
.dc-sidebar {
  width: 220px; min-width: 220px; flex-shrink: 0;
  border-right: 1px solid var(--border-color);
  background: var(--card-bg);
  transition: width 0.22s cubic-bezier(0.4,0,0.2,1), min-width 0.22s cubic-bezier(0.4,0,0.2,1), opacity 0.22s;
  overflow: hidden;
}
.dc-sidebar--hidden { width: 0; min-width: 0; opacity: 0; pointer-events: none; }

/* Body */
.dc-body { flex: 1; min-width: 0; overflow-y: auto; }

.dc-loading {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 12px; padding: 80px 20px; color: var(--text-muted); font-size: 0.875rem;
}
@keyframes dc-spin { to { transform: rotate(360deg); } }
.dc-loading__spinner { width: 24px; height: 24px; border: 2px solid var(--border-color); border-top-color: var(--primary); border-radius: 50%; animation: dc-spin 0.7s linear infinite; }
</style>
