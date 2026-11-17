<script setup>
// Frappe's own list-view Filter button (field / condition / value rows, "+ Add a Filter",
// "Clear Filters", "Apply Filters"). Emits the names of the matching records, or null when
// no filter is set, so the panel can keep its lists loaded and only hide rows.
import { ref, onMounted, onUnmounted } from "vue";

const props = defineProps({
  doctype: { type: String, required: true },
});
const emit = defineEmits(["change"]);

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
  const r = await frappe.call({
    method: "phamos.phamos.page.dev_action_panel.dev_action_panel.get_matching_names",
    args: { doctype: props.doctype, filters },
  });
  if (id === requestId) emit("change", r.message || []);
}

onMounted(async () => {
  await frappe.model.with_doctype(props.doctype);
  buttonRef.value.querySelector(".filter-icon").innerHTML = frappe.utils.icon("es-line-filter", "sm");
  filterGroup = new frappe.ui.FilterGroup({
    doctype: props.doctype,
    filter_button: $(buttonRef.value),
    filter_x_button: $(clearRef.value),
    on_change: onChange,
  });
  // Outside a list view, FilterGroup's clear button empties the filters without on_change.
  $(clearRef.value).on("click", onChange);
});

onUnmounted(() => {
  requestId++;
  $(buttonRef.value).popover?.("hide");
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
