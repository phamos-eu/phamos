<script setup>
import { ref, computed, onMounted } from "vue";

const timesheets = ref([]);
const loading = ref(false);
const employeeName = ref("");

onMounted(async () => {
  employeeName.value = await fetchCurrentEmployee();
  await loadTimesheets();
});

async function fetchCurrentEmployee() {
  const r = await frappe.call({
    method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_current_employee",
  });
  return r.message || "";
}

async function loadTimesheets() {
  loading.value = true;
  const r = await frappe.call({
    method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_my_timesheets",
  });
  timesheets.value = r.message || [];
  loading.value = false;
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
  window.open(`/app/timesheet/${encodeURIComponent(name)}`, "_blank");
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

    <div v-if="loading" class="tl__loading">
      <div class="tl__spinner"></div>
      <span>Loading timesheets…</span>
    </div>

    <div v-else-if="!timesheets.length" class="tl__empty">
      <p class="tl__empty-title">No timesheets found</p>
      <p class="tl__empty-sub">Start a session from an issue to create your first timesheet.</p>
    </div>

    <div v-else class="tl__cards">
      <div
        v-for="ts in timesheets"
        :key="ts.name"
        class="tl__card"
        @click="openTimesheet(ts.name)"
      >
        <div class="tl__card-top">
          <span class="tl__name">{{ ts.name }}</span>
          <span class="tl__badge" :class="`tl__badge--${ts.status_label?.toLowerCase() || 'draft'}`">
            {{ ts.status_label }}
          </span>
        </div>
        <div class="tl__card-meta">
          <span v-if="ts.project_name" class="tl__meta-item">{{ ts.project_name }}</span>
          <span v-if="ts.customer_name" class="tl__meta-item">{{ ts.customer_name }}</span>
          <span class="tl__meta-item">{{ fmtDate(ts.creation) }}</span>
        </div>
        <div class="tl__card-hours">
          <div class="tl__hour">
            <span class="tl__hour-label">Total</span>
            <span class="tl__hour-value">{{ fmtHours(ts.total_hours) }}</span>
          </div>
          <div class="tl__hour">
            <span class="tl__hour-label">Billable</span>
            <span class="tl__hour-value">{{ fmtHours(ts.billable_hours) }}</span>
          </div>
        </div>
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

.tl__cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }
.tl__card {
  background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px;
  padding: 14px; cursor: pointer; transition: box-shadow 0.12s, border-color 0.12s;
}
.tl__card:hover { border-color: var(--primary); box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.tl__card-top {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  margin-bottom: 8px;
}
.tl__name { font-size: 13px; font-weight: 700; color: var(--primary); }
.tl__badge {
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
  padding: 2px 7px; border-radius: 10px;
}
.tl__badge--draft { background: var(--yellow-50, #fefce8); color: var(--yellow-700, #a16207); }
.tl__badge--submitted { background: var(--green-50, #f0fdf4); color: var(--green-700, #15803d); }
.tl__badge--cancelled { background: var(--red-50, #fef2f2); color: var(--red-700, #b91c1c); }

.tl__card-meta {
  display: flex; flex-wrap: wrap; gap: 6px 12px;
  font-size: 12px; color: var(--text-muted); margin-bottom: 12px;
}
.tl__meta-item { display: inline-flex; align-items: center; gap: 4px; }
.tl__meta-item:not(:last-child)::after {
  content: "·"; margin-left: 6px; color: var(--border-color);
}

.tl__card-hours {
  display: flex; gap: 16px;
}
.tl__hour { display: flex; flex-direction: column; }
.tl__hour-label { font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.04em; }
.tl__hour-value { font-size: 14px; font-weight: 700; color: var(--text-color); }
</style>
