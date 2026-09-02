<script setup>
import { computed } from "vue";

const props = defineProps({
  currentView: String,
  mineOnly: Boolean,
  myLeadsCount: Number,
  allLeadsCount: Number,
  activeProjectSession: Object,
  projectElapsedSeconds: Number,
  projectsFilter: String,
  myProjectsCount: Number,
  allProjectsCount: Number,
});

const emit = defineEmits(["change-view", "toggle-mine", "navigate-projects"]);

const user = frappe.session.user;
const userName = frappe.user.full_name() || user;
const userInitial = (userName[0] || "?").toUpperCase();

function fmtElapsed(s) {
  if (!s) return "00:00:00";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
}

function selectLeadView(mineOnly) {
  emit("toggle-mine", mineOnly);
  emit("change-view", "leads");
}

const isRunning = computed(() => props.activeProjectSession?.session_state === "running");

const LEAD_ICON = "M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z";
const ALL_LEADS_ICON = "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z";

const OTHER_VIEWS = [
  { key: "timesheets", label: "My Timesheets", icon: "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" },
  { key: "team",       label: "Team Calendar", icon: "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" },
];
</script>

<template>
  <div class="sb">
    <!-- User info -->
    <div class="sb__user">
      <div class="sb__avatar">{{ userInitial }}</div>
      <div class="sb__user-info">
        <div class="sb__user-name">{{ userName }}</div>
        <div class="sb__user-role">Sales</div>
      </div>
    </div>

    <!-- Active project session widget -->
    <div v-if="activeProjectSession" class="sb__session" :class="isRunning ? 'sb__session--running' : 'sb__session--paused'">
      <div class="sb__session-head">
        <span class="sb__dot" :class="isRunning ? 'dot--green' : 'dot--amber'"></span>
        <span class="sb__session-state">{{ isRunning ? "Running" : "Paused" }}</span>
        <span class="sb__session-type" title="Project">Prj</span>
        <span class="sb__session-timer">{{ fmtElapsed(projectElapsedSeconds) }}</span>
      </div>
      <div class="sb__session-goal">{{ activeProjectSession.goal }}</div>
    </div>

    <!-- Leads section -->
    <div class="sb__section-label">Leads</div>
    <nav class="sb__nav">
      <button
        class="sb__nav-item"
        :class="{ 'sb__nav-item--active': currentView === 'leads' && mineOnly }"
        @click="selectLeadView(true)"
      >
        <svg class="sb__nav-svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path :d="LEAD_ICON"/>
        </svg>
        <span class="sb__nav-label">My Leads</span>
        <span class="sb__nav-count">{{ myLeadsCount }}</span>
      </button>
      <button
        class="sb__nav-item"
        :class="{ 'sb__nav-item--active': currentView === 'leads' && !mineOnly }"
        @click="selectLeadView(false)"
      >
        <svg class="sb__nav-svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path :d="ALL_LEADS_ICON"/>
        </svg>
        <span class="sb__nav-label">All Leads</span>
        <span class="sb__nav-count">{{ allLeadsCount }}</span>
      </button>
    </nav>

    <!-- Other views -->
    <div class="sb__section-label">Views</div>
    <nav class="sb__nav">
      <button
        v-for="view in OTHER_VIEWS"
        :key="view.key"
        class="sb__nav-item"
        :class="{ 'sb__nav-item--active': currentView === view.key }"
        @click="emit('change-view', view.key)"
      >
        <svg class="sb__nav-svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path :d="view.icon"/>
        </svg>
        <span class="sb__nav-label">{{ view.label }}</span>
      </button>
    </nav>

    <!-- Projects -->
    <div class="sb__section-label">Projects</div>
    <nav class="sb__nav">
      <button
        class="sb__nav-item"
        :class="{ 'sb__nav-item--active': currentView === 'projects' && projectsFilter === 'my' }"
        @click="emit('navigate-projects', 'my')"
      >
        <svg class="sb__nav-svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
          <path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z"/>
        </svg>
        <span class="sb__nav-label">My Projects</span>
        <span class="sb__nav-count">{{ myProjectsCount }}</span>
      </button>
      <button
        class="sb__nav-item"
        :class="{ 'sb__nav-item--active': currentView === 'projects' && projectsFilter === 'all' }"
        @click="emit('navigate-projects', 'all')"
      >
        <svg class="sb__nav-svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 7h18M3 12h18M3 17h18"/>
        </svg>
        <span class="sb__nav-label">All Projects</span>
        <span class="sb__nav-count">{{ allProjectsCount }}</span>
      </button>
    </nav>
  </div>
</template>

<style scoped>
.sb {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
  padding: 12px 0 24px;
}

/* User */
.sb__user {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px 12px;
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 8px;
}
.sb__avatar {
  width: 32px; height: 32px; border-radius: 50%;
  background: var(--bg-blue); color: var(--text-on-blue);
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; flex-shrink: 0;
}
.sb__user-name { font-size: 13px; font-weight: 600; color: var(--text-color); line-height: 1.3; }
.sb__user-role { font-size: 11px; color: var(--text-muted); }

/* Active session */
.sb__session {
  margin: 0 10px 8px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  background: var(--control-bg);
}
.sb__session--running { border-color: #16a34a33; background: #f0fdf4; }
.sb__session--paused  { border-color: #d9770633; background: #fffbeb; }
.sb__session-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.sb__dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.dot--green { background: #22c55e; }
.dot--amber { background: #f59e0b; }
.sb__session-state { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); flex: 1; }
.sb__session-type { font-size: 10px; font-weight: 700; color: var(--text-on-blue); background: var(--bg-blue); padding: 1px 5px; border-radius: 4px; }
.sb__session-timer { font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--text-color); }
.sb__session-goal { font-size: 12px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Section labels */
.sb__section-label {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.07em; color: var(--text-muted);
  padding: 10px 16px 4px;
}

/* Nav */
.sb__nav { display: flex; flex-direction: column; gap: 1px; padding: 0 8px; }
.sb__nav-item {
  display: flex; align-items: center; gap: 8px;
  width: 100%; padding: 7px 8px;
  border: none; background: transparent;
  border-radius: 6px; cursor: pointer;
  text-align: left; transition: background 0.1s;
  color: var(--text-muted);
}
.sb__nav-item:hover { background: var(--control-bg); color: var(--text-color); }
.sb__nav-item--active { background: var(--bg-blue); color: var(--text-on-blue); font-weight: 600; }
.sb__nav-item--active .sb__nav-count { background: rgba(255,255,255,0.2); color: var(--text-on-blue); }
.sb__nav-svg { flex-shrink: 0; }
.sb__nav-label { flex: 1; font-size: 13px; }
.sb__nav-count {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 18px; height: 18px; padding: 0 5px;
  background: var(--control-bg); color: var(--text-muted);
  border-radius: 9px; font-size: 10px; font-weight: 700;
}
</style>
