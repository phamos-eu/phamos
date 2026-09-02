<script setup>
import { computed, ref } from "vue";
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

const search = ref("");

const rawProjects = computed(() => (props.filter === "my" ? props.myProjects : props.allProjects) || []);
const query = computed(() => search.value.trim().toLowerCase());

const filteredProjects = computed(() => {
  if (!query.value) return rawProjects.value;
  return rawProjects.value.filter((p) => {
    const haystack = [
      p.project_name || "",
      p.name || "",
      p.customer_name || "",
      p.status || "",
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(query.value);
  });
});
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
          {{ query ? 'No projects match your search' : (filter === 'my' ? 'No projects assigned to you' : 'No open projects found') }}
        </p>
        <p v-if="query" class="pv__empty-sub">Try a different keyword or clear the search above.</p>
      </div>
      <ProjectCard
        v-for="project in filteredProjects"
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
