<script setup>
// Text search box of the Issues and Projects toolbars (#2211); filtering happens in quickSearch.js.
defineProps({ modelValue: { type: String, default: "" }, placeholder: String });
const emit = defineEmits(["update:modelValue"]);
const set = (value) => emit("update:modelValue", value);
</script>

<template>
  <div class="qs">
    <svg class="qs__icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
    </svg>
    <input
      :value="modelValue"
      type="search"
      class="qs__input form-control"
      :placeholder="placeholder"
      :aria-label="placeholder"
      @input="set($event.target.value)"
      @keydown.esc="set('')"
    />
    <button v-if="modelValue" class="qs__clear" title="Clear search" @click="set('')">×</button>
  </div>
</template>

<style scoped>
.qs { flex: 1; min-width: 160px; position: relative; display: flex; align-items: center; }
.qs__input {
  width: 100%;
  padding: 6px 28px 6px 30px;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  background: var(--control-bg);
  color: var(--text-color);
  font-size: 13px;
  line-height: 1.4;
}
/* Our own clear button replaces the browser's. */
.qs__input::-webkit-search-cancel-button { display: none; }
.qs__input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2); }
.qs__icon { position: absolute; left: 9px; pointer-events: none; color: var(--text-muted); }
.qs__clear {
  position: absolute;
  right: 6px;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 50%;
  background: var(--text-muted);
  color: #fff;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.qs__clear:hover { background: var(--text-color); }
</style>
