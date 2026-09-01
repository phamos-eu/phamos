<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import Sidebar from "./components/Sidebar.vue";
import LeadFilterBar from "./components/LeadFilterBar.vue";
import LeadList from "./components/LeadList.vue";

// Shared components imported from dev_action_panel (DRY)
import StatsBar from "../dev_action_panel/components/StatsBar.vue";
import CalendarView from "../dev_action_panel/components/CalendarView.vue";
import TimesheetList from "../dev_action_panel/components/TimesheetList.vue";
import ProjectsView from "../dev_action_panel/components/ProjectsView.vue";
import BreakModal from "../dev_action_panel/components/BreakModal.vue";
import BreakConfirm from "../dev_action_panel/components/BreakConfirm.vue";

// Shared API base path for reused timer/project/stats methods
const DAP = "phamos.phamos.page.dev_action_panel.dev_action_panel";
const SAP = "phamos.phamos.page.sales_action_panel.sales_action_panel";

// ── State ──────────────────────────────────────────────────────────────────
const leads = ref([]);
const stats = ref(null);
const loading = ref(false);
const sidebarOpen = ref(true);
const currentView = ref("leads");
const mineOnly = ref(true);

// Filter state
const searchQuery = ref("");
const statusFilter = ref([]);
const sourceFilter = ref([]);
const ownerFilter = ref([]);
const sortBy = ref("modified");
const sortDir = ref("desc");

function clearAllFilters() {
  searchQuery.value = "";
  statusFilter.value = [];
  sourceFilter.value = [];
  ownerFilter.value = [];
  sortBy.value = "modified";
  sortDir.value = "desc";
}

// Project timer (shared with dev_action_panel)
const myProjects = ref([]);
const allProjects = ref([]);
const projectsFilter = ref("my");
const projectsLoading = ref(false);
const activeProjectSession = ref(null);
const projectElapsedSeconds = ref(0);
let projectTimerInterval = null;

// Break modal state (used by project timer)
const showBreakConfirm = ref(false);
const showBreakModal = ref(false);
const breakFrom = ref(null);

// ── Derived ────────────────────────────────────────────────────────────────
const myLeadsCount = computed(() => leads.value.filter(l => l.is_mine).length);

const statusOptions = computed(() => {
  const set = new Set();
  leads.value.forEach(l => { if (l.status) set.add(l.status); });
  return [...set].sort();
});
const sourceOptions = computed(() => {
  const set = new Set();
  leads.value.forEach(l => { if (l.source) set.add(l.source); });
  return [...set].sort();
});
const ownerOptions = computed(() => {
  const set = new Set();
  leads.value.forEach(l => { if (l.owner_full_name) set.add(l.owner_full_name); });
  return [...set].sort();
});

const filteredLeads = computed(() => {
  let list = mineOnly.value ? leads.value.filter(l => l.is_mine) : leads.value;

  const q = searchQuery.value.trim().toLowerCase();
  if (q) list = list.filter(l =>
    l.lead_name?.toLowerCase().includes(q) ||
    l.company_name?.toLowerCase().includes(q) ||
    l.email_id?.toLowerCase().includes(q) ||
    l.mobile_no?.includes(q) ||
    l.name?.toLowerCase().includes(q)
  );

  if (statusFilter.value.length) list = list.filter(l => statusFilter.value.includes(l.status));
  if (sourceFilter.value.length) list = list.filter(l => sourceFilter.value.includes(l.source));
  if (ownerFilter.value.length) list = list.filter(l => ownerFilter.value.includes(l.owner_full_name));

  list = [...list].sort((a, b) => {
    let va, vb;
    if (sortBy.value === "modified") {
      va = new Date(a.modified).getTime(); vb = new Date(b.modified).getTime();
    } else if (sortBy.value === "lead_name") {
      va = (a.lead_name || "").toLowerCase(); vb = (b.lead_name || "").toLowerCase();
    } else if (sortBy.value === "company") {
      va = (a.company_name || "").toLowerCase(); vb = (b.company_name || "").toLowerCase();
    } else if (sortBy.value === "status") {
      va = (a.status || "").toLowerCase(); vb = (b.status || "").toLowerCase();
    }
    if (va < vb) return sortDir.value === "asc" ? -1 : 1;
    if (va > vb) return sortDir.value === "asc" ? 1 : -1;
    return 0;
  });

  return list;
});

// ── Timer tick ─────────────────────────────────────────────────────────────
function startProjectTick() {
  clearInterval(projectTimerInterval);
  projectTimerInterval = setInterval(() => {
    if (activeProjectSession.value?.session_state === "running") projectElapsedSeconds.value++;
  }, 1000);
}
function stopProjectTick() { clearInterval(projectTimerInterval); projectTimerInterval = null; }

// ── API calls ──────────────────────────────────────────────────────────────
async function loadLeads() {
  loading.value = true;
  const r = await frappe.call({ method: `${SAP}.get_leads` });
  leads.value = r.message || [];
  loading.value = false;
}
async function loadStats() {
  const r = await frappe.call({ method: `${DAP}.get_time_stats` });
  stats.value = r.message || null;
}
async function loadMyProjects() {
  const r = await frappe.call({ method: `${DAP}.get_dev_my_projects` });
  myProjects.value = r.message || [];
}
async function loadAllProjects() {
  const r = await frappe.call({ method: `${DAP}.get_dev_all_projects` });
  allProjects.value = r.message || [];
}
async function loadActiveProjectSession() {
  const r = await frappe.call({ method: `${DAP}.get_active_project_session` });
  activeProjectSession.value = r.message || null;
  if (activeProjectSession.value) {
    projectElapsedSeconds.value = activeProjectSession.value.elapsed_seconds || 0;
    if (activeProjectSession.value.session_state === "running") startProjectTick();
  }
}

// ── Project timer handlers (delegate to dev_action_panel APIs) ─────────────
async function onStartProjectTimer({ project, expectedTime, goal }) {
  const r = await frappe.call({
    method: `${DAP}.start_project_timer`,
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
  const r = await frappe.call({ method: `${DAP}.pause_timer`, args: { name: activeProjectSession.value.name } });
  breakFrom.value = r.message?.break_from || null;
  activeProjectSession.value = { ...activeProjectSession.value, session_state: "paused" };
  stopProjectTick();
}

async function onResumeProjectTimer() {
  if (!activeProjectSession.value) return;
  if (breakFrom.value) {
    showBreakConfirm.value = true;
  } else {
    await doResumeProjectTimer();
  }
}

async function doResumeProjectTimer() {
  await frappe.call({ method: `${DAP}.resume_timer`, args: { name: activeProjectSession.value.name } });
  activeProjectSession.value = { ...activeProjectSession.value, session_state: "running" };
  startProjectTick();
}

async function onStopProjectTimer({ result, percentBillable, activityType }) {
  if (!activeProjectSession.value) return;
  const r = await frappe.call({
    method: `${DAP}.stop_timer`,
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
  await frappe.call({ method: `${DAP}.assign_dev_project`, args: { project_name: project.name } });
  frappe.show_alert({ message: __("Project assigned to you."), indicator: "green" });
  await Promise.all([loadMyProjects(), loadAllProjects()]);
}

// ── Break modal handlers ───────────────────────────────────────────────────
function onBreakConfirmYes() {
  showBreakConfirm.value = false;
  showBreakModal.value = true;
}
async function onBreakConfirmNo() {
  showBreakConfirm.value = false;
  breakFrom.value = null;
  await doResumeProjectTimer();
}
function onBreakConfirmClose() { showBreakConfirm.value = false; }
function onBreakModalClose()   { showBreakModal.value = false; }

async function onBreakSubmit({ project, activityType, goal, result, percentBillable }) {
  showBreakModal.value = false;
  await frappe.call({
    method: `${DAP}.create_break_timesheet`,
    args: { from_time: breakFrom.value, project, goal, result, percent_billable: percentBillable, activity_type: activityType || null },
  });
  breakFrom.value = null;
  await doResumeProjectTimer();
  frappe.show_alert({ message: __("Break timesheet submitted."), indicator: "green" });
}

async function onBreakSkip() {
  showBreakModal.value = false;
  breakFrom.value = null;
  await doResumeProjectTimer();
}

// ── Lifecycle ──────────────────────────────────────────────────────────────
onMounted(async () => {
  await Promise.all([loadLeads(), loadStats(), loadMyProjects(), loadAllProjects(), loadActiveProjectSession()]);
});
onUnmounted(() => { stopProjectTick(); });
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
    <!-- Topbar -->
    <div class="dc-topbar">
      <button class="dc-menu-btn" @click="sidebarOpen = !sidebarOpen" :title="sidebarOpen ? 'Collapse' : 'Expand'">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/></svg>
      </button>
      <span class="dc-topbar-title">Sales Action Panel</span>
    </div>

    <!-- Stats bar (reused) -->
    <StatsBar :stats="stats" />

    <!-- Body: sidebar + main -->
    <div class="dc-split">
      <aside class="dc-sidebar" :class="{ 'dc-sidebar--hidden': !sidebarOpen }">
        <Sidebar
          :current-view="currentView"
          :mine-only="mineOnly"
          :my-leads-count="myLeadsCount"
          :all-leads-count="leads.length"
          :active-project-session="activeProjectSession"
          :project-elapsed-seconds="projectElapsedSeconds"
          :projects-filter="projectsFilter"
          :my-projects-count="myProjects.length"
          :all-projects-count="allProjects.length"
          @change-view="currentView = $event"
          @toggle-mine="mineOnly = $event"
          @navigate-projects="(tab) => { currentView = 'projects'; projectsFilter = tab; }"
        />
      </aside>

      <div class="dc-body">
        <template v-if="currentView === 'leads'">
          <LeadFilterBar
            v-model:search="searchQuery"
            v-model:statusFilter="statusFilter"
            v-model:sourceFilter="sourceFilter"
            v-model:ownerFilter="ownerFilter"
            v-model:sortBy="sortBy"
            v-model:sortDir="sortDir"
            :status-options="statusOptions"
            :source-options="sourceOptions"
            :owner-options="ownerOptions"
            :result-count="filteredLeads.length"
            :total-count="leads.length"
            @clear-all="clearAllFilters"
          />
          <div v-if="loading" class="dc-loading">
            <div class="dc-loading__spinner"></div>
            <span>Loading leads…</span>
          </div>
          <LeadList
            v-else
            :leads="filteredLeads"
            :mine-only="mineOnly"
            @status-changed="({ name, status }) => { const l = leads.find(x => x.name === name); if (l) l.status = status; }"
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
          :active-issue-session="null"
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
  display: flex; flex-direction: column;
  width: 100%; min-height: calc(100vh - 108px);
  background: var(--bg-color);
}

.dc-topbar {
  display: flex; align-items: center; gap: 10px;
  padding: 0 16px; height: 40px;
  border-bottom: 1px solid var(--border-color);
  background: var(--card-bg); flex-shrink: 0;
}
.dc-menu-btn {
  display: flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border: none; background: transparent;
  border-radius: 6px; color: var(--text-muted); cursor: pointer;
  flex-shrink: 0; transition: background 0.12s, color 0.12s;
}
.dc-menu-btn:hover { background: var(--control-bg); color: var(--text-color); }
.dc-topbar-title { font-size: 13px; font-weight: 600; color: var(--text-muted); letter-spacing: -0.01em; }

.dc-split { display: flex; flex: 1; overflow: hidden; min-height: 0; }

.dc-sidebar {
  width: 220px; min-width: 220px; flex-shrink: 0;
  border-right: 1px solid var(--border-color);
  background: var(--card-bg);
  transition: width 0.22s cubic-bezier(0.4,0,0.2,1), min-width 0.22s cubic-bezier(0.4,0,0.2,1), opacity 0.22s;
  overflow: hidden;
}
.dc-sidebar--hidden { width: 0; min-width: 0; opacity: 0; pointer-events: none; }

.dc-body { flex: 1; min-width: 0; overflow-y: auto; }

.dc-loading {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 12px; padding: 80px 20px; color: var(--text-muted); font-size: 0.875rem;
}
@keyframes dc-spin { to { transform: rotate(360deg); } }
.dc-loading__spinner {
  width: 24px; height: 24px; border: 2px solid var(--border-color);
  border-top-color: var(--primary); border-radius: 50%;
  animation: dc-spin 0.7s linear infinite;
}
</style>
