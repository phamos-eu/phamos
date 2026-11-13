<script setup>
import { computed, ref } from "vue";
import ProjectCard from "./ProjectCard.vue";

const props = defineProps({
  // One list: last used first, then assigned to me, then the rest (get_dev_all_projects)
  allProjects: Array,
  activeProjectSession: Object,
  projectElapsedSeconds: Number,
  loading: Boolean,
  activeIssueSession: Object,
  // Project filter shared with the Issues view (#1862): null = all projects
  selectedProject: { type: String, default: null },
  projectOptions: { type: Array, default: () => [] }, // [{ name, title, count }]
});

const emit = defineEmits(["start", "pause", "resume", "stop", "assign", "update:selectedProject"]);

function onProjectFilter(e) {
  emit("update:selectedProject", e.target.value || null);
}

const PROJECT_ICON = "M3 7h18M3 12h18M3 17h18";

const search = ref("");

const rawProjects = computed(() => props.allProjects || []);
const query = computed(() => search.value.trim().toLowerCase());

// The project with my running or paused timer always comes first, whatever the search (#1862).
const filteredProjects = computed(() => {
  const activeName = props.activeProjectSession?.project;
  const active = activeName ? rawProjects.value.find((p) => p.name === activeName) : null;
  const rest = rawProjects.value.filter((p) => p.name !== activeName && matches(p));
  return active ? [active, ...rest] : rest;
});

function matches(p) {
  if (props.selectedProject && p.name !== props.selectedProject) return false;
  if (!query.value) return true;
  const haystack = [p.project_name || "", p.name || "", p.customer_desc || "", p.status || ""]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query.value);
}
</script>

<template>
  <div class="pv">
    <!-- Tab bar matching the Issues tab style -->
    <div class="pv__tabs">
      <button class="pv__tab pv__tab--active" title="Last used first, then projects assigned to you, then the rest">
        <svg class="pv__tab-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <path :d="PROJECT_ICON"/>
        </svg>
        All Projects
        <span class="pv__tab-count">{{ allProjects?.length ?? 0 }}</span>
      </button>
    </div>

    <!-- Search / filter bar -->
    <div class="pv__toolbar">
      <div class="pv__search">
        <svg class="pv__search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
        </svg>
        <input
          v-model="search"
          type="text"
          class="pv__search-input form-control"
          placeholder="Search projects by name, ID, customer or status..."
        />
        <button
          v-if="search"
          class="pv__search-clear"
          title="Clear search"
          @click="search = ''"
        >×</button>
      </div>
      <select
        class="pv__project-filter form-control"
        :class="{ 'pv__project-filter--active': selectedProject }"
        :value="selectedProject || ''"
        title="Filter by project"
        @change="onProjectFilter"
      >
        <option value="">All projects</option>
        <option v-for="p in projectOptions" :key="p.name" :value="p.name">{{ p.title }}</option>
      </select>
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
          {{ query ? 'No projects match your search' : 'No open projects found' }}
        </p>
        <p v-if="query" class="pv__empty-sub">Try a different keyword or clear the search above.</p>
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

/* ── Toolbar / search ───────────────────────────────────────────── */
.pv__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  background: var(--card-bg);
  flex-shrink: 0;
}
.pv__search {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
}
.pv__search-input {
  width: 100%;
  padding: 6px 28px 6px 30px;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  background: var(--control-bg);
  color: var(--text-color);
  font-size: 13px;
  line-height: 1.4;
}
.pv__search-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}
.pv__search-icon {
  position: absolute;
  left: 9px;
  pointer-events: none;
  color: var(--text-muted);
}
.pv__search-clear {
  position: absolute;
  right: 6px;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 50%;
  background: var(--text-muted);
  color: #fff;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.pv__search-clear:hover { background: var(--text-color); }
.pv__project-filter {
  width: auto;
  max-width: 220px;
  height: 32px;
  font-size: 13px;
  flex-shrink: 0;
}
.pv__project-filter--active { border-color: var(--primary); color: var(--primary); font-weight: 600; }

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
