<script setup>
import IssueCard from "./IssueCard.vue";

const props = defineProps({
  issues: Array,
  allCount: Number,
  activeSession: Object,
  elapsedSeconds: Number,
  selectedProject: String,
});

const emit = defineEmits(["start", "pause", "resume", "stop"]);
</script>

<template>
  <div class="il">
    <!-- Empty state -->
    <div v-if="!issues.length" class="il__empty">
      <div class="il__empty-icon">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" opacity="0.3">
          <circle cx="12" cy="12" r="10"/>
          <path d="M8 12h8M12 8v8"/>
        </svg>
      </div>
      <template v-if="selectedProject && allCount">
        <p class="il__empty-title">No issues in this project</p>
        <p class="il__empty-sub">Try selecting "All Issues" from the sidebar</p>
      </template>
      <template v-else>
        <p class="il__empty-title">No open issues assigned to you</p>
        <p class="il__empty-sub">Make sure your Frappe email matches your GitLab assignee, then click <strong>Sync Issues</strong> in the sidebar.</p>
      </template>
    </div>

    <!-- Cards -->
    <div v-else class="il__cards">
      <IssueCard
        v-for="issue in issues"
        :key="issue.name"
        :issue="issue"
        :active-session="activeSession"
        :elapsed-seconds="elapsedSeconds"
        @start="emit('start', $event)"
        @pause="emit('pause')"
        @resume="emit('resume')"
        @stop="emit('stop', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.il { padding: 0; }

.il__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 10px;
}
.il__header-left { display: flex; align-items: center; gap: 8px; }
.il__title { margin: 0; font-size: 14px; font-weight: 700; color: var(--text-color); letter-spacing: -0.01em; }
.il__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  background: var(--control-bg);
  color: var(--text-muted);
  border-radius: 10px;
  font-size: 11px;
  font-weight: 700;
}

/* Empty */
.il__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 72px 24px;
  text-align: center;
}
.il__empty-icon { margin-bottom: 16px; }
.il__empty-title { font-size: 14px; font-weight: 600; color: var(--text-color); margin: 0 0 6px; }
.il__empty-sub { font-size: 13px; color: var(--text-muted); margin: 0; max-width: 360px; line-height: 1.6; }

/* Cards */
.il__cards { padding: 0 16px 24px; display: flex; flex-direction: column; gap: 6px; }
</style>
