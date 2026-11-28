<script setup>
import { computed, ref } from "vue";
import ProjectCard from "./ProjectCard.vue";
import FrappeFilter from "./FrappeFilter.vue";
import QuickSearch from "./QuickSearch.vue";
import { projectMatchesSearch } from "../quickSearch.js";

const props = defineProps({
  // One list: assigned to me first, then the rest; last used first within each (get_dev_all_projects)
  allProjects: Array,
  activeProjectSession: Object,
  projectElapsedSeconds: Number,
  loading: Boolean,
  activeIssueSession: Object,
});

const emit = defineEmits(["start", "pause", "resume", "stop", "assign"]);

const PROJECT_ICON = "M3 7h18M3 12h18M3 17h18";

// Names matching the Filter button, or null when no filter is set.
const matchingNames = ref(null);
// Quick text search next to the Filter button (#2211).
const search = ref("");
const filtering = computed(() => matchingNames.value !== null || !!search.value.trim());

const rawProjects = computed(() => props.allProjects || []);

// The project with my running or paused timer always comes first, whatever the filter.
const filteredProjects = computed(() => {
  const activeName = props.activeProjectSession?.project;
  const active = activeName ? rawProjects.value.find((p) => p.name === activeName) : null;
  const allowed = matchingNames.value && new Set(matchingNames.value);
  const rest = rawProjects.value.filter((p) => p.name !== activeName && (!allowed || allowed.has(p.name)) && projectMatchesSearch(p, search.value));
  return active ? [active, ...rest] : rest;
});
</script>

<template>
  <div class="pv">
    <!-- Tab bar matching the Issues tab style -->
    <div class="pv__tabs">
      <button class="pv__tab pv__tab--active" title="Assigned to you first (including done assignments), then the rest; last used first">
        <svg class="pv__tab-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <path :d="PROJECT_ICON"/>
        </svg>
        All Projects
        <span class="pv__tab-count">{{ allProjects?.length ?? 0 }}</span>
      </button>
    </div>

    <!-- Frappe list-view filter -->
    <div class="pv__toolbar">
      <QuickSearch v-model="search" placeholder="Search projects by name, ID, customer or status…" />
      <FrappeFilter doctype="Project" @change="matchingNames = $event" />
      <span class="pv__count">
        {{ filteredProjects.length }} of {{ rawProjects.length }}
      </span>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="pv__loading">
      <div class="pv__spinner"></div>
      <span>Loading projects…</span>
    </div>

    <!-- Project cards -->
    <div v-else class="pv__cards">
      <div v-if="!filteredProjects.length" class="pv__empty">
        <div class="pv__empty-icon">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" opacity="0.3">
            <circle cx="12" cy="12" r="10"/>
            <path d="M8 12h8M12 8v8"/>
          </svg>
        </div>
        <p class="pv__empty-title">
          {{ filtering ? 'No projects match your filters' : 'No open projects found' }}
        </p>
        <p v-if="filtering" class="pv__empty-sub">Change or clear the search and filters above.</p>
      </div>
      <ProjectCard
        v-for="project in filteredProjects"
        :key="project.name"
        :project="project"
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

/* ── Toolbar ─────────────────────────────────────────────────── */
.pv__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  background: var(--card-bg);
  flex-shrink: 0;
}
.pv__count {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
}

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
