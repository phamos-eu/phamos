<script setup>
import { ref, onMounted, onUnmounted } from "vue";

const calendarRef = ref(null);
const holidaysOnly = ref(false);
const leavesOnly = ref(false);
const loading = ref(true);
const allEvents = ref([]);
const holidays = ref([]);
const leaves = ref([]);

let calendarInstance = null;

onMounted(async () => {
  await loadEvents();
  initCalendar();
});

onUnmounted(() => {
  if (calendarInstance && calendarRef.value) {
    $(calendarRef.value).fullCalendar("destroy");
    calendarInstance = null;
  }
});

async function loadEvents() {
  loading.value = true;
  const r = await frappe.call({
    method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_team_calendar_events",
  });
  holidays.value = r.message?.holidays || [];
  leaves.value = r.message?.leaves || [];
  allEvents.value = [...holidays.value, ...leaves.value];
  loading.value = false;
}

function getVisibleEvents() {
  if (holidaysOnly.value) return holidays.value;
  if (leavesOnly.value) return leaves.value;
  return allEvents.value;
}

function applyFilter() {
  if (!calendarInstance || !calendarRef.value) return;
  const $el = $(calendarRef.value);
  $el.fullCalendar("removeEvents");
  $el.fullCalendar("addEventSource", getVisibleEvents());
}

function initCalendar() {
  if (!calendarRef.value) return;
  frappe.require([
    "/assets/frappe/js/lib/moment/moment.min.js",
    "/assets/frappe/js/lib/fullcalendar/fullcalendar.min.js",
  ], function () {
    frappe.require("/assets/frappe/js/lib/fullcalendar/fullcalendar.min.css");

    const $el = $(calendarRef.value);
    if ($el.data("fullCalendar")) {
      $el.fullCalendar("destroy");
    }

    $el.fullCalendar({
      header: {
        left: "prev,next today",
        center: "title",
        right: "month,agendaWeek,agendaDay",
      },
      buttonIcons: false,
      buttonText: {
        prev: "‹",
        next: "›",
        today: "Today",
        month: "Month",
        week: "Week",
        day: "Day",
      },
      defaultView: "month",
      height: "auto",
      contentHeight: "auto",
      fixedWeekCount: false,
      editable: false,
      eventLimit: false,
      events: getVisibleEvents(),
      eventClick: function (calEvent) {
        frappe.show_alert(calEvent.title);
      },
      eventRender: function (event, element) {
        element.find(".fc-title").html(event.title);
      },
    });

    calendarInstance = $el;
  });
}
</script>

<template>
  <div class="cv">
    <div class="cv__toolbar">
      <div class="cv__legend">
        <span class="cv__legend-item"><span class="cv__dot cv__dot--holiday"></span> Holiday</span>
        <span class="cv__legend-item"><span class="cv__dot cv__dot--half"></span> Half-day leave</span>
        <span class="cv__legend-item"><span class="cv__dot cv__dot--full"></span> Full-day leave</span>
      </div>
      <div class="cv__filters">
        <label class="cv__check">
          <input v-model="holidaysOnly" type="checkbox" @change="leavesOnly = false; applyFilter()" />
          Show only holidays
        </label>
        <label class="cv__check">
          <input v-model="leavesOnly" type="checkbox" @change="holidaysOnly = false; applyFilter()" />
          Show only leaves
        </label>
      </div>
    </div>
    <div v-if="loading" class="cv__loading">
      <div class="cv__spinner"></div>
      <span>Loading team calendar…</span>
    </div>
    <div ref="calendarRef" class="cv__calendar"></div>
  </div>
</template>

<style scoped>
.cv { padding: 12px 16px 24px; }
.cv__toolbar {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  margin-bottom: 12px; flex-wrap: wrap;
}
.cv__legend { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.cv__legend-item { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-color); }
.cv__dot { width: 10px; height: 10px; border-radius: 2px; }
.cv__dot--holiday { background: #28a745; }
.cv__dot--half { background: #ff69b4; }
.cv__dot--full { background: #6b9eeb; }

.cv__filters { display: flex; align-items: center; gap: 16px; }
.cv__check { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-color); cursor: pointer; }
.cv__check input { cursor: pointer; }

.cv__loading {
  display: flex; align-items: center; gap: 10px;
  padding: 24px; color: var(--text-muted); font-size: 13px;
}
.cv__spinner {
  width: 18px; height: 18px; border-radius: 50%;
  border: 2px solid var(--border-color);
  border-top-color: var(--primary);
  animation: cv-spin 0.8s linear infinite;
}
@keyframes cv-spin { to { transform: rotate(360deg); } }

.cv__calendar { min-height: 650px; }
</style>

<style>
/* Make FullCalendar toolbar play nicely with Frappe theming */
.cv__calendar .fc-button {
  text-transform: none !important;
  letter-spacing: 0 !important;
}
.cv__calendar .fc-prev-button,
.cv__calendar .fc-next-button {
  font-size: 20px !important;
  line-height: 1 !important;
  padding: 0 10px !important;
}
</style>
