<script setup>
import { computed } from "vue";

const props = defineProps({
  projects: Array,
  selectedProject: String,
  activeSession: Object,
  elapsedSeconds: Number,
  currentView: String,
  totalIssues: Number,
  myIssuesCount: Number,
  mineOnly: Boolean,
  syncing: Boolean,
  projectsFilter: String,
  myProjectsCount: Number,
  allProjectsCount: Number,
  activeProjectSession: Object,
  projectElapsedSeconds: Number,
});

const emit = defineEmits(["select-project", "change-view", "toggle-mine", "sync", "navigate-projects"]);

const user = frappe.session.user;
const userName = frappe.user.full_name() || user;
const userInitial = (userName[0] || "?").toUpperCase();

function fmtElapsed(s) {
  if (!s) return "00:00:00";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
}

function selectIssueView(mineOnly) {
  emit('toggle-mine', mineOnly);
  emit('change-view', 'issues');
}

// Unified: project session takes precedence if both somehow exist
const displaySession = computed(() => props.activeProjectSession || props.activeSession || null);
const displayElapsed = computed(() => props.activeProjectSession ? props.projectElapsedSeconds : props.elapsedSeconds);
const isRunning = computed(() => displaySession.value?.session_state === "running");
const isProjectSession = computed(() => !!props.activeProjectSession);

const OTHER_VIEWS = [
  { key: "timesheets", label: "My Timesheets", disabled: false, icon: "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" },
  { key: "calendar",   label: "Calendar",      disabled: true, icon: "M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2 2H5a2 2 0 00-2 2v12a2 2 0 002 2z" },
  { key: "kanban",     label: "Kanban",        disabled: true,  icon: "M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" },
  { key: "team",       label: "Team Calendar", disabled: false, icon: "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" },
];

const ISSUE_ICON = "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2";
</script>

<template>
  <div class="sb">
    <!-- User info -->
    <div class="sb__user">
      <div class="sb__avatar">{{ userInitial }}</div>
      <div class="sb__user-info">
        <div class="sb__user-name">{{ userName }}</div>
        <div class="sb__user-role">Developer</div>
      </div>
    </div>

    <!-- Sync button -->
    <div class="sb__sync-wrap">
      <button class="sb__sync-btn" :disabled="syncing" @click="emit('sync')" :title="syncing ? 'Syncing…' : 'Sync GitLab Issues'">
        <svg class="sb__sync-icon" :class="{ spinning: syncing }" width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
          <path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/>
        </svg>
        {{ syncing ? "Refreshing…" : "Refresh" }}
      </button>
    </div>

    <!-- Active session widget -->
    <div v-if="displaySession" class="sb__session" :class="isRunning ? 'sb__session--running' : 'sb__session--paused'">
      <div class="sb__session-head">
        <span class="sb__dot" :class="isRunning ? 'dot--green' : 'dot--amber'"></span>
        <span class="sb__session-state">{{ isRunning ? "Running" : "Paused" }}</span>
        <span v-if="isProjectSession" class="sb__session-type">Project</span>
        <span class="sb__session-timer">{{ fmtElapsed(displayElapsed) }}</span>
      </div>
      <div class="sb__session-goal">{{ displaySession.goal }}</div>
    </div>

    <!-- Issues filter: Mine / All -->
    <div class="sb__section-label">Issues</div>
    <nav class="sb__nav">
      <button
        class="sb__nav-item"
        :class="{ 'sb__nav-item--active': mineOnly }"
        @click="selectIssueView(true)"
      >
        <svg class="sb__nav-svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path :d="ISSUE_ICON"/>
        </svg>
        <span class="sb__nav-label">My Issues</span>
        <span class="sb__nav-count">{{ myIssuesCount }}</span>
      </button>
      <button
        class="sb__nav-item"
        :class="{ 'sb__nav-item--active': !mineOnly }"
        @click="selectIssueView(false)"
      >
        <svg class="sb__nav-svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/>
        </svg>
        <span class="sb__nav-label">All Issues</span>
        <span class="sb__nav-count">{{ totalIssues }}</span>
      </button>
    </nav>

    <!-- Other views (coming soon) -->
    <div class="sb__section-label">Views</div>
    <nav class="sb__nav">
      <button
        v-for="view in OTHER_VIEWS"
        :key="view.key"
        class="sb__nav-item"
        :class="{
          'sb__nav-item--active': currentView === view.key && !view.disabled,
          'sb__nav-item--soon': view.disabled,
        }"
        :disabled="view.disabled"
        @click="emit('change-view', view.key)"
      >
        <svg class="sb__nav-svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path :d="view.icon"/>
        </svg>
        <span class="sb__nav-label">{{ view.label }}</span>
        <span v-if="view.disabled" class="sb__soon">soon</span>
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

    <!-- Filter by Project -->
    <div class="sb__section-label">Filter by Project</div>
    <nav class="sb__nav">
      <button
        class="sb__nav-item"
        :class="{ 'sb__nav-item--active': !selectedProject }"
        @click="emit('select-project', null)"
      >
        <span class="sb__nav-dot"></span>
        <span class="sb__nav-label">All</span>
        <span class="sb__nav-count">{{ mineOnly ? myIssuesCount : totalIssues }}</span>
      </button>
      <button
        v-for="proj in projects"
        :key="proj.name"
        class="sb__nav-item"
        :class="{ 'sb__nav-item--active': selectedProject === proj.name }"
        @click="emit('select-project', proj.name)"
      >
        <span class="sb__nav-dot"></span>
        <span class="sb__nav-label" :title="proj.title">{{ proj.title }}</span>
        <span class="sb__nav-count">{{ proj.count }}</span>
      </button>
      <p v-if="!projects.length" class="sb__empty">No projects</p>
    </nav>

    <div class="sb__spacer"></div>
  </div>
</template>

<style scoped>
.sb { display: flex; flex-direction: column; height: 100%; font-size: 13px; overflow-y: auto; }

/* User */
.sb__user {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 14px 12px; border-bottom: 1px solid var(--border-color); flex-shrink: 0;
}
.sb__avatar {
  width: 32px; height: 32px; border-radius: 50%;
  background: var(--primary); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; flex-shrink: 0;
}
.sb__user-name { font-size: 13px; font-weight: 600; color: var(--text-color); line-height: 1.2; }
.sb__user-role { font-size: 11px; color: var(--text-muted); }

/* Sync */
.sb__sync-wrap { padding: 8px 10px 0; flex-shrink: 0; }
.sb__sync-btn {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  width: 100%; padding: 7px 10px; border: 1px solid var(--border-color);
  border-radius: 7px; background: var(--card-bg); color: var(--text-muted);
  font-size: 12px; font-weight: 500; cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.sb__sync-btn:hover:not(:disabled) { background: var(--control-bg); color: var(--text-color); }
.sb__sync-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.sb__sync-icon { flex-shrink: 0; }
@keyframes sb-spin { to { transform: rotate(360deg); } }
.spinning { animation: sb-spin 0.8s linear infinite; }

/* Active session */
.sb__session { margin: 10px 10px 0; padding: 10px 12px; border-radius: 8px; flex-shrink: 0; }
.sb__session--running { background: var(--green-50, #f0fdf4); border: 1px solid var(--green-200, #bbf7d0); }
.sb__session--paused  { background: var(--yellow-50, #fefce8); border: 1px solid var(--yellow-200, #fef08a); }
.sb__session-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.sb__dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.dot--green { background: var(--green-500, #22c55e); animation: pulse 2s ease-in-out infinite; }
.dot--amber { background: var(--yellow-500, #eab308); }
@keyframes pulse { 0%,100% { box-shadow: 0 0 0 2px rgba(34,197,94,0.25); } 50% { box-shadow: 0 0 0 4px rgba(34,197,94,0.1); } }
.sb__session-state { font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); flex: 1; }
.sb__session-type { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; background: var(--blue-50, #eff6ff); color: var(--primary); border-radius: 3px; padding: 1px 5px; flex-shrink: 0; }
.sb__session-timer { font-family: var(--font-monospace, monospace); font-size: 12.5px; font-weight: 700; color: var(--text-color); }
.sb__session-goal { font-size: 11.5px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Section label */
.sb__section-label { padding: 14px 14px 4px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); flex-shrink: 0; }

/* Nav */
.sb__nav { padding: 2px 6px; flex-shrink: 0; }
.sb__nav-item {
  display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 8px;
  border: none; background: transparent; border-radius: 6px; cursor: pointer;
  color: var(--text-muted); transition: background 0.1s, color 0.1s; text-align: left; margin-bottom: 1px; font-size: 13px;
}
.sb__nav-item:hover:not(:disabled) { background: var(--control-bg); color: var(--text-color); }
.sb__nav-item--active { background: var(--blue-50, #eff6ff); color: var(--primary); font-weight: 600; }
.sb__nav-item--soon { cursor: default; opacity: 0.5; }
.sb__nav-svg { flex-shrink: 0; }
.sb__nav-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sb__nav-count { font-size: 11px; font-weight: 600; background: var(--control-bg); color: var(--text-muted); border-radius: 10px; padding: 1px 6px; flex-shrink: 0; }
.sb__nav-item--active .sb__nav-count { background: var(--primary); color: #fff; }
.sb__soon { font-size: 9.5px; font-weight: 600; background: var(--control-bg); color: var(--text-muted); border-radius: 3px; padding: 1px 5px; text-transform: uppercase; letter-spacing: 0.04em; flex-shrink: 0; }
.sb__nav-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--border-color); flex-shrink: 0; }
.sb__nav-item--active .sb__nav-dot { background: var(--primary); }
.sb__empty { padding: 6px 10px; color: var(--text-muted); font-size: 12px; font-style: italic; }
.sb__spacer { flex: 1; }
</style>

<style>
[data-theme="dark"] .sb__session--running {
  background: rgba(34,197,94,0.1); border-color: rgba(34,197,94,0.25);
}
[data-theme="dark"] .sb__session--paused {
  background: rgba(234,179,8,0.1); border-color: rgba(234,179,8,0.25);
}
/* Active nav: neutral white tint + left accent border — readable regardless of ambient light */
[data-theme="dark"] .sb__nav-item--active {
  background: rgba(255,255,255,0.08);
  color: #e2e8f0;
  box-shadow: inset 3px 0 0 #60a5fa;
  font-weight: 600;
}
[data-theme="dark"] .sb__nav-item--active .sb__nav-count {
  background: rgba(255,255,255,0.12);
  color: #cbd5e1;
}
[data-theme="dark"] .sb__nav-item--active .sb__nav-dot {
  background: #60a5fa;
}
</style>
