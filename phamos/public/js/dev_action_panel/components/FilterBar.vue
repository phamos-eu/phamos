<script setup>
import { ref, computed, onBeforeUnmount } from "vue";

const props = defineProps({
  search: String,
  dueFilter: String,
  assigneeFilter: Array,
  labelFilter: Array,
  sortBy: String,
  sortDir: String,
  assigneeOptions: Array,
  labelOptions: Array,
  resultCount: Number,
  totalCount: Number,
});

const emit = defineEmits([
  "update:search", "update:dueFilter", "update:assigneeFilter",
  "update:labelFilter", "update:sortBy", "update:sortDir", "clear-all",
]);

const activeDropdown = ref(null);
const assigneeSearch = ref("");
const labelSearch = ref("");

const DUE_OPTIONS = [
  { value: "all",       label: "Any date" },
  { value: "overdue",   label: "Overdue" },
  { value: "today",     label: "Due today" },
  { value: "this_week", label: "Due this week" },
  { value: "no_due",    label: "No due date" },
];

const SORT_OPTIONS = [
  { value: "due_date:asc",  label: "Due date", dir: "asc",  icon: "↑" },
  { value: "due_date:desc", label: "Due date", dir: "desc", icon: "↓" },
  { value: "id:asc",        label: "Issue ID", dir: "asc",  icon: "↑" },
  { value: "id:desc",       label: "Issue ID", dir: "desc", icon: "↓" },
  { value: "project:asc",   label: "Project",  dir: "asc",  icon: "A–Z" },
  { value: "title:asc",     label: "Title",    dir: "asc",  icon: "A–Z" },
];

const sortKey = computed(() => `${props.sortBy}:${props.sortDir}`);
const activeSortLabel = computed(() => {
  const o = SORT_OPTIONS.find(o => o.value === sortKey.value);
  return o ? `${o.label} ${o.icon}` : "Sort";
});
const activeDueLabel = computed(() => {
  const o = DUE_OPTIONS.find(o => o.value === props.dueFilter);
  return o?.value !== "all" ? o?.label : null;
});

const filteredAssigneeOptions = computed(() => {
  const q = assigneeSearch.value.trim().toLowerCase();
  return q ? (props.assigneeOptions || []).filter(n => n.toLowerCase().includes(q)) : (props.assigneeOptions || []);
});
const filteredLabelOptions = computed(() => {
  const q = labelSearch.value.trim().toLowerCase();
  return q ? (props.labelOptions || []).filter(l => l.toLowerCase().includes(q)) : (props.labelOptions || []);
});

const hasActiveFilters = computed(() =>
  props.search || props.dueFilter !== "all" ||
  (props.assigneeFilter?.length) || (props.labelFilter?.length) ||
  props.sortBy !== "due_date" || props.sortDir !== "asc"
);

// Multi-select toggles
function toggleAssignee(val) {
  const cur = props.assigneeFilter || [];
  emit("update:assigneeFilter", cur.includes(val) ? cur.filter(v => v !== val) : [...cur, val]);
}
function clearAssignees() { emit("update:assigneeFilter", []); }

function toggleLabel(val) {
  const cur = props.labelFilter || [];
  emit("update:labelFilter", cur.includes(val) ? cur.filter(v => v !== val) : [...cur, val]);
}
function clearLabels() { emit("update:labelFilter", []); }

function toggleDropdown(name) {
  if (activeDropdown.value === name) { activeDropdown.value = null; return; }
  activeDropdown.value = name;
  setTimeout(() => document.addEventListener("click", closeAll, { once: true }), 0);
}
function closeAll() {
  activeDropdown.value = null;
  assigneeSearch.value = "";
  labelSearch.value = "";
}
onBeforeUnmount(() => document.removeEventListener("click", closeAll));

function setSort(opt) { emit("update:sortBy", opt.value.split(":")[0]); emit("update:sortDir", opt.dir); activeDropdown.value = null; }
function setDue(val) { emit("update:dueFilter", val); activeDropdown.value = null; }
function clearAll() { emit("clear-all"); activeDropdown.value = null; assigneeSearch.value = ""; labelSearch.value = ""; }
</script>

<template>
  <div class="fb">
    <div class="fb__bar" @click.stop>

      <!-- Search icon -->
      <svg class="fb__search-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
      </svg>

      <!-- Active filter chips -->
      <span v-if="activeDueLabel" class="fb__chip">
        {{ activeDueLabel }}
        <button class="fb__chip-remove" @click.stop="setDue('all')">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </button>
      </span>

      <span v-if="assigneeFilter && assigneeFilter.length === 1" class="fb__chip fb__chip--assignee">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/></svg>
        {{ assigneeFilter[0] }}
        <button class="fb__chip-remove" @click.stop="clearAssignees">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </button>
      </span>
      <span v-else-if="assigneeFilter && assigneeFilter.length > 1" class="fb__chip fb__chip--assignee">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/></svg>
        {{ assigneeFilter.length }} assignees
        <button class="fb__chip-remove" @click.stop="clearAssignees">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </button>
      </span>

      <span v-if="labelFilter && labelFilter.length === 1" class="fb__chip fb__chip--label">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M17.63 5.84C17.27 5.33 16.67 5 16 5L5 5.01C3.9 5.01 3 5.9 3 7v10c0 1.1.9 1.99 2 1.99L16 19c.67 0 1.27-.33 1.63-.84L22 12l-4.37-6.16z"/></svg>
        {{ labelFilter[0] }}
        <button class="fb__chip-remove" @click.stop="clearLabels">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </button>
      </span>
      <span v-else-if="labelFilter && labelFilter.length > 1" class="fb__chip fb__chip--label">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M17.63 5.84C17.27 5.33 16.67 5 16 5L5 5.01C3.9 5.01 3 5.9 3 7v10c0 1.1.9 1.99 2 1.99L16 19c.67 0 1.27-.33 1.63-.84L22 12l-4.37-6.16z"/></svg>
        {{ labelFilter.length }} labels
        <button class="fb__chip-remove" @click.stop="clearLabels">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </button>
      </span>

      <!-- Search input -->
      <input
        class="fb__input"
        type="text"
        placeholder="Search issues…"
        :value="search"
        @input="emit('update:search', $event.target.value)"
        spellcheck="false"
        autocomplete="off"
      />

      <!-- Clear all -->
      <button v-if="hasActiveFilters" class="fb__clear" @click="clearAll" title="Clear all filters">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
      </button>

      <!-- Result count -->
      <span class="fb__count">{{ resultCount }} of {{ totalCount }}</span>

      <!-- Divider -->
      <div class="fb__divider"></div>

      <!-- Due date filter -->
      <div class="fb__dd-wrap" @click.stop>
        <button class="fb__filter-btn" :class="{ 'fb__filter-btn--active': dueFilter !== 'all' }" @click="toggleDropdown('due')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
          Due date
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" class="fb__chevron" :class="{ 'fb__chevron--open': activeDropdown === 'due' }"><path d="M7 10l5 5 5-5z"/></svg>
        </button>
        <Transition name="dd">
          <div v-if="activeDropdown === 'due'" class="fb__menu" @click.stop>
            <button
              v-for="opt in DUE_OPTIONS" :key="opt.value"
              class="fb__menu-item"
              :class="{ 'fb__menu-item--active': dueFilter === opt.value }"
              @click="setDue(opt.value)"
            >
              <span class="fb__menu-check">
                <svg v-if="dueFilter === opt.value" width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
              </span>
              {{ opt.label }}
            </button>
          </div>
        </Transition>
      </div>

      <!-- Assignee filter -->
      <div v-if="assigneeOptions && assigneeOptions.length" class="fb__dd-wrap" @click.stop>
        <button
          class="fb__filter-btn"
          :class="{ 'fb__filter-btn--active': assigneeFilter && assigneeFilter.length }"
          @click="toggleDropdown('assignee')"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/></svg>
          Assignee
          <span v-if="assigneeFilter && assigneeFilter.length" class="fb__filter-badge">{{ assigneeFilter.length }}</span>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" class="fb__chevron" :class="{ 'fb__chevron--open': activeDropdown === 'assignee' }"><path d="M7 10l5 5 5-5z"/></svg>
        </button>
        <Transition name="dd">
          <div v-if="activeDropdown === 'assignee'" class="fb__menu fb__menu--searchable" @click.stop>
            <div class="fb__menu-search">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
              <input
                v-model="assigneeSearch"
                class="fb__menu-search-input"
                placeholder="Search assignees…"
                spellcheck="false"
                autocomplete="off"
                @click.stop
              />
              <button v-if="assigneeSearch" class="fb__menu-search-clear" @click.stop="assigneeSearch = ''">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
              </button>
            </div>
            <div class="fb__menu-scroll">
              <p v-if="!filteredAssigneeOptions.length" class="fb__menu-empty">No results</p>
              <button
                v-for="name in filteredAssigneeOptions" :key="name"
                class="fb__menu-item"
                :class="{ 'fb__menu-item--checked': assigneeFilter && assigneeFilter.includes(name) }"
                @click="toggleAssignee(name)"
              >
                <span class="fb__menu-checkbox" :class="{ 'fb__menu-checkbox--on': assigneeFilter && assigneeFilter.includes(name) }">
                  <svg v-if="assigneeFilter && assigneeFilter.includes(name)" width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
                </span>
                {{ name }}
              </button>
            </div>
            <div v-if="assigneeFilter && assigneeFilter.length" class="fb__menu-footer">
              <button class="fb__menu-footer-clear" @click.stop="clearAssignees">Clear selection</button>
            </div>
          </div>
        </Transition>
      </div>

      <!-- Label filter -->
      <div v-if="labelOptions && labelOptions.length" class="fb__dd-wrap" @click.stop>
        <button
          class="fb__filter-btn"
          :class="{ 'fb__filter-btn--active': labelFilter && labelFilter.length }"
          @click="toggleDropdown('label')"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M17.63 5.84C17.27 5.33 16.67 5 16 5L5 5.01C3.9 5.01 3 5.9 3 7v10c0 1.1.9 1.99 2 1.99L16 19c.67 0 1.27-.33 1.63-.84L22 12l-4.37-6.16z"/></svg>
          Label
          <span v-if="labelFilter && labelFilter.length" class="fb__filter-badge">{{ labelFilter.length }}</span>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" class="fb__chevron" :class="{ 'fb__chevron--open': activeDropdown === 'label' }"><path d="M7 10l5 5 5-5z"/></svg>
        </button>
        <Transition name="dd">
          <div v-if="activeDropdown === 'label'" class="fb__menu fb__menu--right fb__menu--searchable" @click.stop>
            <div class="fb__menu-search">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
              <input
                v-model="labelSearch"
                class="fb__menu-search-input"
                placeholder="Search labels…"
                spellcheck="false"
                autocomplete="off"
                @click.stop
              />
              <button v-if="labelSearch" class="fb__menu-search-clear" @click.stop="labelSearch = ''">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
              </button>
            </div>
            <div class="fb__menu-scroll">
              <p v-if="!filteredLabelOptions.length" class="fb__menu-empty">No results</p>
              <button
                v-for="lbl in filteredLabelOptions" :key="lbl"
                class="fb__menu-item"
                :class="{ 'fb__menu-item--checked': labelFilter && labelFilter.includes(lbl) }"
                @click="toggleLabel(lbl)"
              >
                <span class="fb__menu-checkbox" :class="{ 'fb__menu-checkbox--on': labelFilter && labelFilter.includes(lbl) }">
                  <svg v-if="labelFilter && labelFilter.includes(lbl)" width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
                </span>
                {{ lbl }}
              </button>
            </div>
            <div v-if="labelFilter && labelFilter.length" class="fb__menu-footer">
              <button class="fb__menu-footer-clear" @click.stop="clearLabels">Clear selection</button>
            </div>
          </div>
        </Transition>
      </div>

      <!-- Sort dropdown -->
      <div class="fb__dd-wrap" @click.stop>
        <button class="fb__filter-btn" :class="{ 'fb__filter-btn--active': sortBy !== 'due_date' || sortDir !== 'asc' }" @click="toggleDropdown('sort')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M7 12h10M11 18h2"/></svg>
          {{ activeSortLabel }}
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" class="fb__chevron" :class="{ 'fb__chevron--open': activeDropdown === 'sort' }"><path d="M7 10l5 5 5-5z"/></svg>
        </button>
        <Transition name="dd">
          <div v-if="activeDropdown === 'sort'" class="fb__menu fb__menu--right" @click.stop>
            <div class="fb__menu-label">Sort by</div>
            <button
              v-for="opt in SORT_OPTIONS" :key="opt.value"
              class="fb__menu-item"
              :class="{ 'fb__menu-item--active': sortKey === opt.value }"
              @click="setSort(opt)"
            >
              <span class="fb__menu-check">
                <svg v-if="sortKey === opt.value" width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
              </span>
              <span>{{ opt.label }}</span>
              <span class="fb__menu-dir">{{ opt.icon }}</span>
            </button>
          </div>
        </Transition>
      </div>

    </div>
  </div>
</template>

<style scoped>
.fb { padding: 8px 16px 4px; }

.fb__bar {
  display: flex; align-items: center; gap: 6px;
  background: var(--card-bg); border: 1px solid var(--border-color);
  border-radius: 8px; padding: 0 10px; height: 36px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.fb__bar:focus-within { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,0.08); }

.fb__search-icon { color: var(--text-muted); flex-shrink: 0; }

/* Chips */
.fb__chip {
  display: inline-flex; align-items: center; gap: 4px;
  background: var(--blue-50, #eff6ff); color: var(--primary);
  border: 1px solid var(--blue-200, #bfdbfe); border-radius: 4px;
  font-size: 11.5px; font-weight: 600; padding: 2px 4px 2px 7px;
  flex-shrink: 0; white-space: nowrap; max-width: 140px;
}
.fb__chip > span:not(.fb__chip-remove) { overflow: hidden; text-overflow: ellipsis; }
.fb__chip-remove {
  display: flex; align-items: center; justify-content: center;
  background: none; border: none; cursor: pointer; color: var(--primary);
  padding: 1px; border-radius: 2px; opacity: 0.7; transition: opacity 0.1s; flex-shrink: 0;
}
.fb__chip-remove:hover { opacity: 1; }

/* Search input */
.fb__input {
  flex: 1; min-width: 0; border: none; background: transparent;
  font-size: 13px; color: var(--text-color); outline: none; font-family: inherit;
}
.fb__input::placeholder { color: var(--text-muted); }

/* Clear */
.fb__clear {
  display: flex; align-items: center; justify-content: center;
  background: none; border: none; cursor: pointer; color: var(--text-muted);
  padding: 3px; border-radius: 4px; flex-shrink: 0; transition: background 0.1s, color 0.1s;
}
.fb__clear:hover { background: var(--control-bg); color: var(--text-color); }

/* Count */
.fb__count { font-size: 11.5px; color: var(--text-muted); white-space: nowrap; flex-shrink: 0; }

/* Divider */
.fb__divider { width: 1px; height: 18px; background: var(--border-color); flex-shrink: 0; margin: 0 2px; }

/* Dropdown wrapper */
.fb__dd-wrap { position: relative; flex-shrink: 0; }

/* Filter buttons */
.fb__filter-btn {
  display: inline-flex; align-items: center; gap: 5px;
  background: none; border: none; cursor: pointer;
  font-size: 12.5px; font-weight: 500; color: var(--text-muted);
  padding: 4px 6px; border-radius: 5px; white-space: nowrap;
  transition: background 0.1s, color 0.1s;
}
.fb__filter-btn:hover,
.fb__filter-btn--active { background: var(--control-bg); color: var(--text-color); }
.fb__filter-btn--active { color: var(--primary); font-weight: 600; }

.fb__filter-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 16px; height: 16px; padding: 0 4px;
  background: var(--primary); color: #fff;
  border-radius: 8px; font-size: 10px; font-weight: 700; line-height: 1;
}

.fb__chevron { transition: transform 0.15s; flex-shrink: 0; color: var(--text-muted); }
.fb__chevron--open { transform: rotate(180deg); }

/* Dropdown menu */
.fb__menu {
  position: absolute; top: calc(100% + 6px); left: 0;
  min-width: 200px; background: var(--card-bg);
  border: 1px solid var(--border-color); border-radius: 8px;
  box-shadow: var(--shadow-md, 0 4px 16px rgba(0,0,0,0.12));
  z-index: 500; overflow: hidden;
}
.fb__menu--right { left: auto; right: 0; }
.fb__menu--searchable { padding: 0; }

/* In-menu search */
.fb__menu-search {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 10px; border-bottom: 1px solid var(--border-color);
  color: var(--text-muted);
}
.fb__menu-search-input {
  flex: 1; border: none; background: transparent; outline: none;
  font-size: 12.5px; color: var(--text-color); font-family: inherit;
}
.fb__menu-search-input::placeholder { color: var(--text-muted); }
.fb__menu-search-clear {
  display: flex; align-items: center; background: none; border: none;
  cursor: pointer; color: var(--text-muted); padding: 1px; border-radius: 2px;
  opacity: 0.7; transition: opacity 0.1s;
}
.fb__menu-search-clear:hover { opacity: 1; }

/* Scrollable list */
.fb__menu-scroll { max-height: 220px; overflow-y: auto; padding: 4px; }

/* Footer (clear selection) */
.fb__menu-footer {
  border-top: 1px solid var(--border-color); padding: 6px 8px;
}
.fb__menu-footer-clear {
  width: 100%; background: none; border: none; cursor: pointer;
  font-size: 12px; color: var(--text-muted); text-align: left;
  padding: 4px 6px; border-radius: 4px; transition: background 0.1s, color 0.1s;
}
.fb__menu-footer-clear:hover { background: var(--control-bg); color: var(--text-color); }

.fb__menu-empty { padding: 10px 12px; color: var(--text-muted); font-size: 12px; font-style: italic; margin: 0; }

.fb__menu-label {
  font-size: 10.5px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--text-muted); padding: 6px 10px 4px;
}

/* Menu items */
.fb__menu-item {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 7px 10px; background: none; border: none; cursor: pointer;
  font-size: 13px; color: var(--text-color); border-radius: 5px; text-align: left;
  transition: background 0.1s;
}
.fb__menu-item:hover { background: var(--control-bg); }
.fb__menu-item--active { color: var(--primary); font-weight: 600; }
.fb__menu-item--checked { font-weight: 600; }

.fb__menu-check {
  width: 16px; height: 16px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; color: var(--primary);
}

/* Checkbox style for multi-select */
.fb__menu-checkbox {
  width: 14px; height: 14px; flex-shrink: 0;
  border: 1.5px solid var(--border-color); border-radius: 3px;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.1s, border-color 0.1s;
}
.fb__menu-checkbox--on {
  background: var(--primary); border-color: var(--primary); color: #fff;
}

.fb__menu-dir { margin-left: auto; font-size: 11px; color: var(--text-muted); }

/* Dropdown animation */
.dd-enter-active, .dd-leave-active { transition: opacity 0.12s, transform 0.12s; }
.dd-enter-from, .dd-leave-to { opacity: 0; transform: translateY(-4px); }
</style>

<style>
[data-theme="dark"] .fb__chip {
  background: rgba(255,255,255,0.1); border-color: rgba(255,255,255,0.18); color: #e2e8f0;
}
[data-theme="dark"] .fb__chip-remove { color: #cbd5e1; }
[data-theme="dark"] .fb__menu { box-shadow: 0 4px 20px rgba(0,0,0,0.45); }
[data-theme="dark"] .fb__menu-item--active { color: #93c5fd; }
[data-theme="dark"] .fb__menu-item--checked { color: #e2e8f0; }
[data-theme="dark"] .fb__menu-check { color: #93c5fd; }
[data-theme="dark"] .fb__menu-checkbox--on { background: #3b82f6; border-color: #3b82f6; }
[data-theme="dark"] .fb__filter-btn--active { color: #93c5fd; }
[data-theme="dark"] .fb__filter-badge { background: #3b82f6; }
</style>
