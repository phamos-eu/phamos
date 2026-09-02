<script setup>
import { ref, onBeforeUnmount } from "vue";

const props = defineProps({ lead: Object });
const emit = defineEmits(["status-changed"]);

const LEAD_STATUSES = [
  "Lead", "Open", "Replied", "Opportunity", "Quotation",
  "Lost Quotation", "Interested", "Converted", "Do Not Contact",
];

// Delegate to frappe.utils.guess_colour for exact ERPNext list-view parity
function statusColor(status) {
  return frappe.utils.guess_colour(status) || "gray";
}

// ── Inline status picker ────────────────────────────────────────────────────
const statusPickerOpen = ref(false);
const saving = ref(false);

function togglePicker(e) {
  e.stopPropagation();
  statusPickerOpen.value = !statusPickerOpen.value;
  if (statusPickerOpen.value) {
    document.addEventListener("click", closePicker, { once: true });
  }
}

function closePicker() { statusPickerOpen.value = false; }

async function selectStatus(e, newStatus) {
  e.stopPropagation();
  if (newStatus === props.lead.status || saving.value) return;
  saving.value = true;
  closePicker();
  try {
    await frappe.call({
      method: "phamos.phamos.page.sales_action_panel.sales_action_panel.set_lead_status",
      args: { lead_name: props.lead.name, status: newStatus },
    });
    emit("status-changed", { name: props.lead.name, status: newStatus });
  } catch (_) {
    frappe.show_alert({ message: __("Failed to update status"), indicator: "red" });
  } finally {
    saving.value = false;
  }
}

onBeforeUnmount(() => document.removeEventListener("click", closePicker));

function openLead() {
  frappe.set_route("Form", "Lead", props.lead.name);
}

function fmtDate(dtStr) {
  if (!dtStr) return "";
  const parts = dtStr.split(/[- :]/).map(Number);
  if (parts.length < 3) return dtStr;
  const [y, mo, dd] = parts;
  return new Date(y, mo - 1, dd).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}
</script>

<template>
  <div class="lc" :class="{ 'lc--mine': lead.is_mine }" @click="openLead">
    <div class="lc__header">
      <div class="lc__name-wrap">
        <span class="lc__name">{{ lead.lead_name || lead.name }}</span>
        <span v-if="lead.company_name" class="lc__company">{{ lead.company_name }}</span>
      </div>

      <!-- Status badge — click opens inline picker -->
      <div class="lc__status-wrap" @click.stop>
        <button
          class="lc__status indicator-pill"
          :class="[statusColor(lead.status), { 'lc__status--saving': saving }]"
          :title="saving ? 'Saving…' : 'Click to change status'"
          @click="togglePicker"
        >
          {{ lead.status }}
          <svg class="lc__status-caret" width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><path d="M7 10l5 5 5-5z"/></svg>
        </button>

        <div v-if="statusPickerOpen" class="lc__picker" @click.stop>
          <button
            v-for="s in LEAD_STATUSES"
            :key="s"
            class="lc__picker-item"
            :class="{ 'lc__picker-item--active': s === lead.status }"
            @click="selectStatus($event, s)"
          >
            <span class="indicator-pill no-indicator-dot" :class="statusColor(s)">{{ s }}</span>
          </button>
        </div>
      </div>
    </div>

    <div class="lc__meta">
      <span v-if="lead.owner_full_name" class="lc__meta-item" title="Lead Owner">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/>
        </svg>
        {{ lead.owner_full_name }}
        <span v-if="lead.is_mine" class="indicator-pill blue no-indicator-dot lc__me-badge">me</span>
      </span>
      <span v-if="lead.source" class="lc__meta-item" title="Source">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
        </svg>
        {{ lead.source }}
      </span>
      <span v-if="lead.territory" class="lc__meta-item" title="Territory">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
        </svg>
        {{ lead.territory }}
      </span>
      <span v-if="lead.email_id" class="lc__meta-item lc__meta-item--contact" :title="lead.email_id">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>
        </svg>
        {{ lead.email_id }}
      </span>
      <span v-if="lead.mobile_no" class="lc__meta-item lc__meta-item--contact" :title="lead.mobile_no">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/>
        </svg>
        {{ lead.mobile_no }}
      </span>
    </div>

    <div class="lc__footer">
      <span class="lc__date">Modified {{ fmtDate(lead.modified) }}</span>
      
    </div>
  </div>
</template>

<style scoped>
.lc {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 12px 14px 10px;
  cursor: pointer;
  transition: box-shadow 0.15s, border-color 0.15s;
}
.lc:hover { box-shadow: 0 2px 10px rgba(0,0,0,.07); border-color: var(--primary-light); }
.lc--mine { border-left: 3px solid var(--primary); }

/* Header */
.lc__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.lc__name-wrap { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.lc__name { font-size: 13px; font-weight: 600; color: var(--text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.lc__company { font-size: 12px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Status badge + picker */
.lc__status-wrap { position: relative; flex-shrink: 0; }
.lc__status {
  border: none;
  cursor: pointer;
  font-size: 11px !important;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 8px !important;
  height: auto !important;
  transition: opacity 0.15s;
}
.lc__status:hover { opacity: 0.85; }
.lc__status--saving { opacity: 0.5; pointer-events: none; }
.lc__status-caret { opacity: 0.6; flex-shrink: 0; }

.lc__picker {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 200;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,.14);
  padding: 4px 0;
  min-width: 160px;
}
.lc__picker-item {
  display: block;
  width: 100%;
  background: none;
  border: none;
  padding: 4px 8px;
  text-align: left;
  cursor: pointer;
  transition: background 0.1s;
}
.lc__picker-item:hover { background: var(--control-bg); }
.lc__picker-item--active { background: var(--control-bg); }

/* Meta row */
.lc__meta { display: flex; flex-wrap: wrap; gap: 6px 12px; margin-bottom: 8px; }
.lc__meta-item {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11.5px; color: var(--text-color);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 200px;
}
.lc__meta-item--contact { max-width: 220px; }
.lc__me-badge { font-size: 10px !important; padding: 1px 6px !important; height: auto !important; line-height: 1.4 !important; }

/* Footer */
.lc__footer { display: flex; align-items: center; justify-content: space-between; }
.lc__date { font-size: 11px; color: var(--text-muted); }
.lc__open-btn {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11.5px; font-weight: 600; color: var(--primary);
  background: var(--primary-light); border: none;
  padding: 3px 10px; border-radius: 5px; cursor: pointer;
  transition: opacity 0.1s;
}
.lc__open-btn:hover { opacity: 0.8; }
</style>
