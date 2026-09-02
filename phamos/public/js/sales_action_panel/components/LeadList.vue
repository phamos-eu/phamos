<script setup>
import LeadCard from "./LeadCard.vue";

defineProps({
  leads: Array,
  mineOnly: Boolean,
});

const emit = defineEmits(["status-changed"]);
</script>

<template>
  <div class="ll">
    <div v-if="!leads.length" class="ll__empty">
      <div class="ll__empty-icon">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" opacity="0.3">
          <circle cx="12" cy="12" r="10"/>
          <path d="M8 12h8M12 8v8"/>
        </svg>
      </div>
      <p class="ll__empty-title">{{ mineOnly ? "No leads assigned to you" : "No leads found" }}</p>
      <p class="ll__empty-sub">
        {{ mineOnly
          ? "Leads where you are the Lead Owner will appear here."
          : "Try clearing your filters or check if leads exist." }}
      </p>
    </div>

    <div v-else class="ll__cards">
      <LeadCard
        v-for="lead in leads"
        :key="lead.name"
        :lead="lead"
        @status-changed="emit('status-changed', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.ll { padding: 0; }

.ll__empty {
  display: flex; flex-direction: column; align-items: center;
  padding: 72px 24px; text-align: center;
}
.ll__empty-icon { margin-bottom: 16px; }
.ll__empty-title { font-size: 14px; font-weight: 600; color: var(--text-color); margin: 0 0 6px; }
.ll__empty-sub { font-size: 13px; color: var(--text-muted); margin: 0; max-width: 360px; line-height: 1.6; }

.ll__cards { padding: 0 16px 24px; display: flex; flex-direction: column; gap: 6px; }
</style>
