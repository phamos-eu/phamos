<script setup>
// Frappe's own list-view Filter button (field / condition / value rows, "+ Add a Filter",
// "Clear Filters", "Apply Filters"). Emits the names of the matching records, or null when
// no filter is set, so the panel can keep its lists loaded and only hide rows.
import { ref, onMounted, onBeforeUnmount } from "vue";

const props = defineProps({
  doctype: { type: String, required: true },
});
const emit = defineEmits(["change"]);

// The fields the server lets the panel filter on: FILTERABLE_FIELDS in dev_action_panel.py
// (the fields the panel already shows). Keep both lists in sync.
const FILTERABLE_FIELDS = {
  "GitLab Issue": [
    "name", "issue_id", "title", "state", "due_date", "start_date",
    "assignee", "assignee_email", "gitlab_username",
    "issue_url", "parent_issue", "gitlab_project", "labels",
  ],
  Project: ["name", "project_name", "status", "percent_billable", "customer"],
};

const buttonRef = ref(null);
const clearRef = ref(null);
let filterGroup = null;
let requestId = 0;

async function onChange() {
  const filters = filterGroup.get_filters().map((f) => f.slice(0, 4));
  if (!filters.length) {
    requestId++;
    emit("change", null);
    return;
  }
  const id = ++requestId;
  try {
    const r = await frappe.call({
      method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_matching_names",
      args: { doctype: props.doctype, filters },
    });
    if (id === requestId) emit("change", r.message || []);
  } catch (e) {
    // frappe.call has shown the server's message; keep the list as it is.
  }
}

// Docfields for the field dropdown, so it offers only FILTERABLE_FIELDS (and also works for
// users without read permission on the doctype, for whom Frappe would list no fields).
function filterFields(doctype) {
  return (FILTERABLE_FIELDS[doctype] || [])
    .map((fieldname) =>
      fieldname === "name"
        ? { fieldname: "name", label: "ID", fieldtype: "Link", options: doctype, parent: doctype }
        : frappe.meta.get_docfield(doctype, fieldname)
    )
    .filter(Boolean);
}

onMounted(async () => {
  await frappe.model.with_doctype(props.doctype);
  if (!buttonRef.value) return; // the view was left while the doctype loaded
  buttonRef.value.querySelector(".filter-icon").innerHTML = frappe.utils.icon("es-line-filter", "sm");
  filterGroup = new frappe.ui.FilterGroup({
    doctype: props.doctype,
    filter_button: $(buttonRef.value),
    filter_x_button: $(clearRef.value),
    on_change: onChange,
  });
  // FilterGroup has no option for the field list, but each frappe.ui.Filter it creates takes
  // filter_fields (passed on to its FieldSelect). Inject it for this group's filters only.
  const fields = filterFields(props.doctype);
  const pushNewFilter = filterGroup._push_new_filter;
  filterGroup._push_new_filter = function (...args) {
    const Filter = frappe.ui.Filter;
    frappe.ui.Filter = class extends Filter {
      constructor(opts) {
        super({ ...opts, filter_fields: fields });
      }
    };
    try {
      return pushNewFilter.apply(this, args);
    } finally {
      frappe.ui.Filter = Filter;
    }
  };
  // Outside a list view, FilterGroup's clear button empties the filters without on_change.
  $(clearRef.value).on("click", onChange);
});

// Before unmount, while the buttons still exist.
onBeforeUnmount(() => {
  requestId++;
  $(clearRef.value).off("click", onChange);
  filterGroup?.hide_popover();
});
</script>

<template>
  <div class="ff filter-section">
    <div class="filter-selector">
      <div class="btn-group">
        <button ref="buttonRef" class="btn btn-default btn-sm filter-button">
          <span class="filter-icon"></span>
          <span class="button-label hidden-xs">Filter</span>
        </button>
        <button ref="clearRef" class="btn btn-default btn-sm filter-x-button" title="Clear all filters">
          <span class="filter-x-icon">×</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ff { display: inline-flex; }
.ff .btn-group { display: inline-flex; }
</style>
