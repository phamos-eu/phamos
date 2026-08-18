<script setup>
import ProjectCard from "./ProjectCard.vue";

const props = defineProps({
  filter: String, // 'my' | 'all'
  myProjects: Array,
  allProjects: Array,
  activeProjectSession: Object,
  projectElapsedSeconds: Number,
  loading: Boolean,
  activeIssueSession: Object,
});

const emit = defineEmits(["change-filter", "start", "pause", "resume", "stop", "assign"]);

const PROJECT_ICON = "M3 7h18M3 12h18M3 17h18";
const MY_ICON     = "M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z";
</script>

<template>
  <div class="pv">
    <!-- Tab bar matching the Issues tab style -->
    <div class="pv__tabs">
      <button
        class="pv__tab"
        :class="{ 'pv__tab--active': filter === 'my' }"
        @click="emit('change-filter', 'my')"
      >
        <svg class="pv__tab-icon" width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
          <path :d="MY_ICON"/>
        </svg>
        My Projects
        <span class="pv__tab-count">{{ myProjects?.length ?? 0 }}</span>
      </button>
      <button
        class="pv__tab"
        :class="{ 'pv__tab--active': filter === 'all' }"
        @click="emit('change-filter', 'all')"
      >
        <svg class="pv__tab-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <path :d="PROJECT_ICON"/>
        </svg>
        All Projects
        <span class="pv__tab-count">{{ allProjects?.length ?? 0 }}</span>
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="pv__loading">
      <div class="pv__spinner"></div>
      <span>Loading projects…</span>
    </div>

    <!-- Project cards -->
    <div v-else class="pv__cards">
      <div v-if="!(filter === 'my' ? myProjects : allProjects)?.length" class="pv__empty">
        <div class="pv__empty-icon">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" opacity="0.3">
            <circle cx="12" cy="12" r="10"/>
            <path d="M8 12h8M12 8v8"/>
          </svg>
        </div>
        <p class="pv__empty-title">
          {{ filter === 'my' ? 'No projects assigned to you' : 'No open projects found' }}
        </p>
      </div>
      <ProjectCard
        v-for="project in (filter === 'my' ? myProjects : allProjects)"
        :key="project.name"
        :project="project"
        :mode="filter"
        :active-project-session="activeProjectSession"
        :project-elapsed-seconds="projectElapsedSeconds"
        :active-issue-session="activeIssueSession"
        @start="emit('start', $event)"
        @pause="emit('pause')"
        @resume="emit('resume')"
        @stop="emit('stop', $event)"
        @assign="emit('assign', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.pv { display: flex; flex-direction: column; min-height: 0; }

/* ── Tab bar ───────────────────────────────────────────────────── */
.pv__tabs {
  display: flex;
  gap: 2px;
  padding: 12px 16px 0;
  border-bottom: 1px solid var(--border-color);
  background: var(--card-bg);
  flex-shrink: 0;
}
.pv__tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: none;
  background: transparent;
  border-radius: 8px 8px 0 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color 0.12s, border-color 0.12s;
}
.pv__tab:hover { color: var(--text-color); }
.pv__tab--active { color: var(--primary); font-weight: 600; border-bottom-color: var(--primary); }
.pv__tab-icon { flex-shrink: 0; }
.pv__tab-count {
  font-size: 11px; font-weight: 700;
  background: var(--control-bg); color: var(--text-muted);
  border-radius: 10px; padding: 1px 6px;
}
.pv__tab--active .pv__tab-count { background: var(--primary); color: #fff; }

/* ── Loading ───────────────────────────────────────────────────── */
.pv__loading {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 12px; padding: 80px 20px; color: var(--text-muted); font-size: 0.875rem;
}
.pv__spinner {
  width: 28px; height: 28px; border: 3px solid var(--border-color);
  border-top-color: var(--primary); border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Cards ─────────────────────────────────────────────────────── */
.pv__cards { padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; }

/* ── Empty state ───────────────────────────────────────────────── */
.pv__empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 80px 20px; }
.pv__empty-icon { opacity: 0.5; }
.pv__empty-title { margin: 0; font-size: 14px; font-weight: 600; color: var(--text-muted); }
.pv__empty-sub   { margin: 0; font-size: 13px; color: var(--text-muted); }
</style>
