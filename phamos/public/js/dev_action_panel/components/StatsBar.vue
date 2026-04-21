<script setup>
defineProps({ stats: Object });

function fmt(s) {
  if (!s) return "0s";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h) return `${h}h ${String(m).padStart(2,"0")}m ${String(sec).padStart(2,"0")}s`;
  if (m) return `${m}m ${String(sec).padStart(2,"0")}s`;
  return `${sec}s`;
}
function billPct(period) {
  if (!period?.total_seconds) return 0;
  return Math.min(100, Math.round((period.billable_seconds / period.total_seconds) * 100));
}
function nonBill(period) {
  return Math.max(0, (period?.total_seconds || 0) - (period?.billable_seconds || 0));
}

const PERIODS = [
  { key: "today", label: "Today" },
  { key: "week",  label: "This Week" },
  { key: "month", label: "This Month" },
];
</script>

<template>
  <div v-if="stats" class="sc">
    <div v-for="p in PERIODS" :key="p.key" class="sc__card">
      <div class="sc__head">
        <span class="sc__label">{{ p.label }}</span>
        <span class="sc__total">{{ fmt(stats[p.key]?.total_seconds) }}</span>
      </div>
      <div class="sc__bar">
        <div class="sc__bar-bill"  :style="{ width: billPct(stats[p.key]) + '%' }"></div>
        <div class="sc__bar-rest" :style="{ width: (100 - billPct(stats[p.key])) + '%' }"></div>
      </div>
      <div class="sc__foot">
        <span class="sc__pill sc__pill--bill">
          <span class="sc__pip sc__pip--bill"></span>
          {{ fmt(stats[p.key]?.billable_seconds) }} billable
        </span>
        <span class="sc__pill sc__pill--nb">
          <span class="sc__pip sc__pip--nb"></span>
          {{ fmt(nonBill(stats[p.key])) }} non-billable
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sc {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0;
  border-bottom: 1px solid var(--border-color);
  background: var(--card-bg);
  flex-shrink: 0;
}

.sc__card {
  padding: 14px 20px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-right: 1px solid var(--border-color);
}
.sc__card:last-child { border-right: none; }

/* Head */
.sc__head { display: flex; align-items: baseline; justify-content: space-between; }
.sc__label {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.07em; color: var(--text-muted);
}
.sc__total {
  font-size: 20px; font-weight: 700; color: var(--text-color);
  letter-spacing: -0.03em; font-variant-numeric: tabular-nums;
}

/* Bar */
.sc__bar {
  display: flex; height: 4px; border-radius: 2px; overflow: hidden;
  background: var(--control-bg);
}
.sc__bar-bill { background: #22c55e; border-radius: 2px 0 0 2px; transition: width 0.4s ease; }
.sc__bar-rest { background: #f59e0b; border-radius: 0 2px 2px 0; transition: width 0.4s ease; }

/* Foot pills */
.sc__foot { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sc__pill {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11.5px; color: var(--text-muted);
}
.sc__pip {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
}
.sc__pip--bill { background: #22c55e; }
.sc__pip--nb   { background: #f59e0b; }
.sc__pill--bill { color: #16a34a; font-weight: 600; }
.sc__pill--nb   { color: #d97706; }
</style>
