<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from "vue";

const timesheets = ref([]);
const loading = ref(false);
const loadingMore = ref(false);
const employeeName = ref("");
const hasMore = ref(false);
const currentOffset = ref(0);

function getTodayDate() {
  const today = new Date();
  return today.toISOString().split('T')[0];
}

const fromDate = ref(getTodayDate());
const toDate = ref(getTodayDate());

watch([fromDate, toDate], () => {
  loadTimesheets();
});

const handleVisibilityChange = () => {
  if (!document.hidden) {
    loadTimesheets();
  }
};

onMounted(async () => {
  employeeName.value = await fetchCurrentEmployee();
  await loadTimesheets();
  document.addEventListener('visibilitychange', handleVisibilityChange);
});

onUnmounted(() => {
  document.removeEventListener('visibilitychange', handleVisibilityChange);
});

async function fetchCurrentEmployee() {
  const r = await frappe.call({
    method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_current_employee",
  });
  return r.message || "";
}

async function loadTimesheets(isLoadMore = false) {
  if (isLoadMore) {
    loadingMore.value = true;
  } else {
    loading.value = true;
    timesheets.value = [];
    currentOffset.value = 0;
  }
  
  const r = await frappe.call({
    method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_my_timesheets",
    args: {
      from_date: fromDate.value,
      to_date: toDate.value,
      offset: currentOffset.value,
    },
  });
  
  if (r.message) {
    const response = r.message;
    if (isLoadMore) {
      timesheets.value.push(...(response.timesheets || []));
    } else {
      timesheets.value = response.timesheets || [];
    }
    hasMore.value = response.has_more || false;
    currentOffset.value = (response.offset || 0) + (response.total_on_page || 0);
  }
  
  loading.value = false;
  loadingMore.value = false;
}

async function loadMore() {
  await loadTimesheets(true);
}


function fmtDate(iso) {
  if (!iso) return "—";
  return frappe.datetime.str_to_user(iso.split(".")[0]);
}

function fmtHours(val) {
  const n = parseFloat(val) || 0;
  if (n <= 0) return "0h";
  const h = Math.floor(n);
  const m = Math.round((n - h) * 60);
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

function openTimesheet(name) {
  frappe.set_route("Form", "Timesheet", name);
}

function openDeskList() {
  frappe.route_options = employeeName.value ? { employee: employeeName.value } : {};
  frappe.set_route("List", "Timesheet");
}

const totals = computed(() => {
  return timesheets.value.reduce(
    (acc, t) => {
      acc.hours += parseFloat(t.total_hours) || 0;
      acc.billable += parseFloat(t.billable_hours) || 0;
      return acc;
    },
    { hours: 0, billable: 0 }
  );
});
</script>

<template>
  <div class="tl">
    <div class="tl__header">
      <div>
        <h2 class="tl__title">My Timesheets</h2>
        <p class="tl__subtitle">
          {{ timesheets.length }} records ·
          {{ fmtHours(totals.hours) }} total ·
          {{ fmtHours(totals.billable) }} billable
        </p>
      </div>
      <button class="tl__desk-btn" @click="openDeskList">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
          <path d="M19 19H5V5h7V3H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/>
        </svg>
        Open in Desk
      </button>
    </div>

    <div class="tl__filter-bar">
      <div class="tl__filter-group">
        <label class="tl__filter-label">From Date</label>
        <input 
          v-model="fromDate" 
          type="date" 
          class="tl__filter-input"
        />
      </div>
      <div class="tl__filter-group">
        <label class="tl__filter-label">To Date</label>
        <input 
          v-model="toDate" 
          type="date" 
          class="tl__filter-input"
        />
      </div>
    </div>

    <div v-if="loading" class="tl__loading">
      <div class="tl__spinner"></div>
      <span>Loading timesheets…</span>
    </div>

    <div v-else-if="!timesheets.length" class="tl__empty">
      <p class="tl__empty-title">No timesheets found</p>
      <p class="tl__empty-sub">Start a session from an issue to create your first timesheet.</p>
    </div>

    <div v-else class="tl__list">
      <div
        v-for="ts in timesheets"
        :key="ts.name"
        class="tl__list-item"
        @click="openTimesheet(ts.name)"
      >
        <div class="tl__list-content">
          <div class="tl__list-left">
            <h3 class="tl__list-title">{{ ts.name }}</h3>
            <p class="tl__list-meta">
              <span v-if="ts.project_name" class="tl__list-meta-item">{{ ts.project_name }}</span>
              <span v-if="ts.customer_name" class="tl__list-meta-item">{{ ts.customer_name }}</span>
              <span class="tl__list-meta-item">{{ fmtDate(ts.creation) }}</span>
            </p>
          </div>
          <div class="tl__list-right">
            <div class="tl__list-stats">
              <div class="tl__list-stat">
                <span class="tl__list-label">Total</span>
                <span class="tl__list-value">{{ fmtHours(ts.total_hours) }}</span>
              </div>
              <div class="tl__list-stat">
                <span class="tl__list-label">Billable</span>
                <span class="tl__list-value">{{ fmtHours(ts.billable_hours) }}</span>
              </div>
            </div>
            <span class="tl__list-badge" :class="`tl__list-badge--${ts.status_label?.toLowerCase() || 'draft'}`">
              {{ ts.status_label }}
            </span>
          </div>
        </div>
      </div>

      <div v-if="hasMore" class="tl__load-more-wrapper">
        <button 
          class="tl__load-more-btn" 
          @click="loadMore"
          :disabled="loadingMore"
        >
          <span v-if="loadingMore" class="tl__load-more-spinner"></span>
          <span v-else>Load more timesheets</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tl { padding: 12px 16px 24px; }
.tl__header {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
  margin-bottom: 16px;
}
.tl__title { margin: 0; font-size: 15px; font-weight: 700; color: var(--text-color); }
.tl__subtitle { margin: 4px 0 0; font-size: 12px; color: var(--text-muted); }
.tl__desk-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 14px; border-radius: 7px;
  font-size: 13px; font-weight: 600; cursor: pointer;
  border: 1px solid var(--border-color); background: var(--card-bg); color: var(--text-color);
  transition: background 0.12s, border-color 0.12s;
}
.tl__desk-btn:hover { background: var(--control-bg); }

.tl__filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: flex-end;
}

.tl__filter-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tl__filter-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.tl__filter-input {
  padding: 6px 8px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--card-bg);
  color: var(--text-color);
  font-size: 13px;
  font-family: inherit;
  transition: border-color 0.12s, background 0.12s;
}

.tl__filter-input:hover {
  border-color: var(--text-muted);
}

.tl__filter-input:focus {
  outline: none;
  border-color: var(--primary);
  background: var(--control-bg);
}

.tl__loading {
  display: flex; align-items: center; gap: 10px;
  padding: 32px; color: var(--text-muted); font-size: 13px;
}
.tl__spinner {
  width: 18px; height: 18px; border-radius: 50%;
  border: 2px solid var(--border-color); border-top-color: var(--primary);
  animation: tl-spin 0.8s linear infinite;
}
@keyframes tl-spin { to { transform: rotate(360deg); } }

.tl__empty {
  display: flex; flex-direction: column; align-items: center;
  padding: 64px 24px; text-align: center;
}
.tl__empty-title { font-size: 14px; font-weight: 600; color: var(--text-color); margin: 0 0 6px; }
.tl__empty-sub { font-size: 13px; color: var(--text-muted); margin: 0; }

.tl__list { }
.tl__list-item {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: box-shadow 0.12s, border-color 0.12s;
}
.tl__list-item:hover {
  border-color: var(--primary);
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.tl__load-more-wrapper {
  display: flex;
  justify-content: center;
  padding: 16px 0 8px;
}

.tl__load-more-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid var(--border-color);
  background: var(--card-bg);
  color: var(--text-color);
  transition: background 0.12s, border-color 0.12s, color 0.12s;
}

.tl__load-more-btn:hover:not(:disabled) {
  background: var(--control-bg);
  border-color: var(--primary);
  color: var(--primary);
}

.tl__load-more-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.tl__load-more-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-color);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: tl-spin 0.8s linear infinite;
}

.tl__list-content {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}
.tl__list-left {
  flex: 1;
}
.tl__list-title {
  margin: 0 0 4px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--primary);
}
.tl__list-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
}
.tl__list-meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.tl__list-meta-item:not(:last-child)::after {
  content: "·";
  margin-left: 6px;
  color: var(--border-color);
}
.tl__list-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}
.tl__list-stats {
  display: flex;
  gap: 16px;
}
.tl__list-stat {
  display: flex;
  flex-direction: column;
}
.tl__list-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-muted);
  letter-spacing: 0.04em;
}
.tl__list-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-color);
}
.tl__list-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 2px 6px;
  border-radius: 4px;
}
.tl__list-badge--draft {
  background: var(--red-50, #fff0f0);
  color: var(--red-700, #b52a2a);
}
.tl__list-badge--submitted {
  background: var(--blue-50, #edf6fd);
  color: var(--blue-700, #0070cc);
}
.tl__list-badge--cancelled {
  background: var(--red-50, #fef2f2);
  color: var(--red-700, #b91c1c);
}

[data-theme="dark"] .tl__list-badge--draft,
[data-theme="dark"] .tl__list-badge--cancelled {
  background: #cc2929;
  color: #fff7f7;
}

[data-theme="dark"] .tl__list-badge--submitted {
  background: #007be0;
  color: #f7fbfd;
}
</style>
