<script setup>
// Frappe's own Datetime control (the picker of the Project Action Panel) inside the Vue panel.
// v-model is a system time zone string "YYYY-MM-DD HH:mm:ss", the format the backend stores;
// the control shows and takes the time in the user's time zone and converts on its own.
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps({
  modelValue: { type: String, default: "" },
});
const emit = defineEmits(["update:modelValue"]);

const el = ref(null);
let control = null;
let settingFromProp = false;

function setValue(value) {
  if (!control) return;
  settingFromProp = true;
  Promise.resolve(control.set_value(value || "")).finally(() => {
    settingFromProp = false;
  });
}

onMounted(() => {
  control = frappe.ui.form.make_control({
    parent: el.value,
    df: {
      fieldtype: "Datetime",
      fieldname: "dap_datetime",
      // The panel labels already name the time zone.
      hide_timezone: 1,
      onchange: () => {
        if (settingFromProp) return;
        emit("update:modelValue", control.get_value() || "");
      },
    },
    render_input: true,
    only_input: true,
  });
  setValue(props.modelValue);
});

watch(
  () => props.modelValue,
  (value) => {
    if (control && (value || "") !== (control.get_value() || "")) setValue(value);
  }
);

onBeforeUnmount(() => {
  control?.datepicker?.destroy?.();
  control = null;
});
</script>

<template>
  <div ref="el" class="fdt"></div>
</template>

<style scoped>
.fdt :deep(input) {
  min-width: 190px;
  font-variant-numeric: tabular-nums;
}
</style>
