<script setup>
// GitLab ticket on Stop of a project timer (#1862): pick a ticket by number or title, or paste its
// URL / group/project#N. The server says which issue is the child and which the parent
// (phamos.gitlab_integration.issue_refs.preview_reference); the same rule links them on Stop.
import { ref, computed, watch, onBeforeUnmount } from "vue";

const props = defineProps({
  modelValue: { type: String, default: "" }, // GitLab Issue name, URL or group/project#N
  issues: { type: Array, default: () => [] }, // issues loaded in the panel (get_my_issues)
  project: { type: String, default: "" },     // ERPNext project of the timer: its tickets come first
});
const emit = defineEmits(["update:modelValue"]);

const text = ref("");
const open = ref(false);
const preview = ref(null); // { child, parent, found }
const checking = ref(false);
let timer = null;
let seq = 0;

const REF_RE = /^(https?:\/\/\S+\/-\/(issues|work_items)\/\d+|[\w.-]+(\/[\w.-]+)+#\d+)$/;

const suggestions = computed(() => {
  const q = text.value.trim().replace(/^#/, "").toLowerCase();
  if (!q || REF_RE.test(text.value.trim())) return [];
  return props.issues
    .filter(i => String(i.issue_id).startsWith(q) || (i.title || "").toLowerCase().includes(q))
    .sort((a, b) => (b.project === props.project) - (a.project === props.project))
    .slice(0, 8);
});

function pick(issue) {
  text.value = `#${issue.issue_id} ${issue.title}`;
  open.value = false;
  emit("update:modelValue", issue.name);
  check(issue.name);
}

function onInput() {
  open.value = true;
  preview.value = null;
  const value = text.value.trim();
  clearTimeout(timer);
  if (REF_RE.test(value)) {
    emit("update:modelValue", value);
    timer = setTimeout(() => check(value), 300);
  } else {
    emit("update:modelValue", "");
  }
}

async function check(reference) {
  const mine = ++seq;
  checking.value = true;
  try {
    const r = await frappe.call({
      method: "phamos.gitlab_integration.issue_refs.preview_reference",
      args: { reference },
    });
    if (mine === seq) preview.value = r.message || null;
  } finally {
    if (mine === seq) checking.value = false;
  }
}

function clear() {
  text.value = "";
  preview.value = null;
  emit("update:modelValue", "");
}

function onBlur() { setTimeout(() => { open.value = false; }, 150); }

watch(() => props.modelValue, v => { if (!v) { text.value = ""; preview.value = null; } });
onBeforeUnmount(() => clearTimeout(timer));

const otherProject = computed(() => {
  const p = preview.value;
  const linked = p?.child || p?.parent;
  return linked && linked.project && props.project && linked.project !== props.project;
});
</script>

<template>
  <div class="gt">
    <div class="gt__input-wrap">
      <input
        v-model="text"
        class="gt__input"
        placeholder="#123, title or GitLab URL (optional)"
        spellcheck="false"
        autocomplete="off"
        @input="onInput"
        @focus="open = true"
        @blur="onBlur"
      />
      <button v-if="text" class="gt__clear" type="button" title="Clear" @click="clear">×</button>
    </div>
    <ul v-if="open && suggestions.length" class="gt__menu">
      <li v-for="i in suggestions" :key="i.name" class="gt__item" @mousedown.prevent="pick(i)">
        <span class="gt__id">#{{ i.issue_id }}</span>
        <span class="gt__title">{{ i.title }}</span>
        <span class="gt__kind">{{ i.child_count > 0 ? 'parent' : (i.parent_issue ? 'child' : '') }}</span>
      </li>
    </ul>
    <div v-if="checking" class="gt__preview gt__preview--muted">Checking ticket…</div>
    <div v-else-if="preview && preview.found" class="gt__preview">
      <span v-if="preview.child" class="gt__chip gt__chip--child" :title="preview.child.issue_url">Child #{{ preview.child.issue_id }} {{ preview.child.title }}</span>
      <span v-if="preview.parent" class="gt__chip gt__chip--parent" :title="preview.parent.issue_url">Parent #{{ preview.parent.issue_id }} {{ preview.parent.title }}</span>
      <span v-if="otherProject" class="gt__warn">This ticket belongs to another project.</span>
    </div>
    <div v-else-if="preview && !preview.found" class="gt__preview gt__preview--warn">
      Ticket not found. Check the URL; the project may not be connected to GitLab yet.
    </div>
  </div>
</template>

<style scoped>
.gt { position: relative; width: 100%; }
.gt__input-wrap { position: relative; }
.gt__input {
  width: 100%; height: 34px; padding: 0 28px 0 10px; font-size: 13px;
  border: 1px solid var(--border-color); border-radius: 6px;
  background: var(--control-bg); color: var(--text-color); outline: none;
}
.gt__input:focus { border-color: var(--primary); }
.gt__clear {
  position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
  border: none; background: none; cursor: pointer; color: var(--text-muted); font-size: 16px;
}
.gt__menu {
  position: absolute; z-index: 600; left: 0; right: 0; top: 38px; margin: 0; padding: 4px;
  list-style: none; background: var(--card-bg); border: 1px solid var(--border-color);
  border-radius: 8px; box-shadow: var(--shadow-md, 0 4px 16px rgba(0,0,0,0.12)); max-height: 240px; overflow-y: auto;
}
.gt__item { display: flex; gap: 8px; align-items: center; padding: 6px 8px; border-radius: 5px; cursor: pointer; font-size: 13px; }
.gt__item:hover { background: var(--control-bg); }
.gt__id { color: var(--text-muted); font-variant-numeric: tabular-nums; flex-shrink: 0; }
.gt__title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt__kind { font-size: 11px; color: var(--text-muted); flex-shrink: 0; }
.gt__preview { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; font-size: 12px; }
.gt__preview--muted { color: var(--text-muted); }
.gt__preview--warn, .gt__warn { color: #b45309; }
.gt__chip { padding: 2px 8px; border-radius: 10px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt__chip--child { background: rgba(37, 99, 235, 0.1); color: #1d4ed8; }
.gt__chip--parent { background: rgba(22, 163, 74, 0.12); color: #15803d; }
</style>
