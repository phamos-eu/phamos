<script setup>
import { ref, computed, onBeforeUnmount } from "vue";

const props = defineProps({
  search: String,
  dueFilter: String,  // 'all' | 'overdue' | 'today' | 'this_week' | 'no_due'
  sortBy: String,     // 'due_date' | 'id' | 'project' | 'title'
  sortDir: String,    // 'asc' | 'desc'
  resultCount: Number,
  totalCount: Number,
});

const emit = defineEmits(["update:search", "update:dueFilter", "update:sortBy", "update:sortDir", "clear-all"]);

const activeDropdown = ref(null); // 'due' | 'sort'

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

const hasActiveFilters = computed(() =>
  props.search || props.dueFilter !== "all" || props.sortBy !== "due_date" || props.sortDir !== "asc"
);

function toggleDropdown(name) {
  if (activeDropdown.value === name) {
    activeDropdown.value = null;
    return;
  }
  activeDropdown.value = name;
  setTimeout(() => {
    document.addEventListener("click", closeAll, { once: true });
  }, 0);
}
function closeAll() { activeDropdown.value = null; }
onBeforeUnmount(() => document.removeEventListener("click", closeAll));

function setSort(opt) {
  emit("update:sortBy", opt.value.split(":")[0]);
  emit("update:sortDir", opt.dir);
  activeDropdown.value = null;
}
function setDue(val) {
  emit("update:dueFilter", val);
  activeDropdown.value = null;
}
function clearAll() {
  emit("clear-all");
  activeDropdown.value = null;
}
</script>

<template>
  <div class="fb">
    <!-- Search + filter chip row -->
    <div class="fb__bar">
      <!-- Search icon -->
      <svg class="fb__search-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
      </svg>

      <!-- Active due filter chip -->
      <span v-if="activeDueLabel" class="fb__chip">
        {{ activeDueLabel }}
        <button class="fb__chip-remove" @click.stop="setDue('all')">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </button>
      </span>

      <!-- Search input -->
      <input
        class="fb__input"
        type="text"
        placeholder="Search by title or issue #…"
        :value="search"
        @input="emit('update:search', $event.target.value)"
        spellcheck="false"
        autocomplete="off"
      />

      <!-- Clear all (when any filter active) -->
      <button v-if="hasActiveFilters" class="fb__clear" @click="clearAll" title="Clear all filters">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
      </button>

      <!-- Result count -->
      <span class="fb__count">{{ resultCount }} of {{ totalCount }}</span>

      <!-- Divider -->
      <div class="fb__divider"></div>

      <!-- Due date filter dropdown -->
      <div class="fb__dd-wrap" @click.stop>
        <button class="fb__filter-btn" :class="{ 'fb__filter-btn--active': dueFilter !== 'all' }" @click="toggleDropdown('due')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
          Due date
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" class="fb__chevron" :class="{ 'fb__chevron--open': activeDropdown === 'due' }"><path d="M7 10l5 5 5-5z"/></svg>
        </button>
        <Transition name="dd">
          <div v-if="activeDropdown === 'due'" class="fb__menu" @click.stop>
            <button
              v-for="opt in DUE_OPTIONS"
              :key="opt.value"
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
              v-for="opt in SORT_OPTIONS"
              :key="opt.value"
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
.fb {
  padding: 8px 16px 4px;
}

/* Main bar */
.fb__bar {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 0 10px;
  height: 36px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.fb__bar:focus-within {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37,99,235,0.08);
}

.fb__search-icon {
  color: var(--text-muted);
  flex-shrink: 0;
}

/* Chip for active filter inside bar */
.fb__chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--blue-50, #eff6ff);
  color: var(--primary);
  border: 1px solid var(--blue-200, #bfdbfe);
  border-radius: 4px;
  font-size: 11.5px;
  font-weight: 600;
  padding: 2px 4px 2px 7px;
  flex-shrink: 0;
  white-space: nowrap;
}
.fb__chip-remove {
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--primary);
  padding: 1px;
  border-radius: 2px;
  opacity: 0.7;
  transition: opacity 0.1s;
}
.fb__chip-remove:hover { opacity: 1; }

/* Search input */
.fb__input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  font-size: 13px;
  color: var(--text-color);
  outline: none;
  font-family: inherit;
}
.fb__input::placeholder { color: var(--text-muted); }

/* Clear button */
.fb__clear {
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  padding: 3px;
  border-radius: 4px;
  flex-shrink: 0;
  transition: background 0.1s, color 0.1s;
}
.fb__clear:hover { background: var(--control-bg); color: var(--text-color); }

/* Result count */
.fb__count {
  font-size: 11.5px;
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

/* Divider */
.fb__divider {
  width: 1px;
  height: 18px;
  background: var(--border-color);
  flex-shrink: 0;
  margin: 0 2px;
}

/* Dropdown wrapper */
.fb__dd-wrap {
  position: relative;
  flex-shrink: 0;
}

/* Filter/sort trigger buttons */
.fb__filter-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-muted);
  padding: 4px 6px;
  border-radius: 5px;
  white-space: nowrap;
  transition: background 0.1s, color 0.1s;
}
.fb__filter-btn:hover,
.fb__filter-btn--active { background: var(--control-bg); color: var(--text-color); }
.fb__filter-btn--active { color: var(--primary); font-weight: 600; }

.fb__chevron { transition: transform 0.15s; flex-shrink: 0; color: var(--text-muted); }
.fb__chevron--open { transform: rotate(180deg); }

/* Dropdown menu */
.fb__menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  min-width: 180px;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: var(--shadow-md, 0 4px 16px rgba(0,0,0,0.12));
  z-index: 500;
  padding: 4px;
  overflow: hidden;
}
.fb__menu--right { left: auto; right: 0; }

.fb__menu-label {
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  padding: 6px 10px 4px;
}

.fb__menu-item {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 7px 10px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-color);
  border-radius: 5px;
  text-align: left;
  transition: background 0.1s;
}
.fb__menu-item:hover { background: var(--control-bg); }
.fb__menu-item--active { color: var(--primary); font-weight: 600; }
.fb__menu-check {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary);
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
[data-theme="dark"] .fb__menu {
  box-shadow: 0 4px 20px rgba(0,0,0,0.45);
}
[data-theme="dark"] .fb__menu-item--active { color: #93c5fd; }
[data-theme="dark"] .fb__menu-check { color: #93c5fd; }
[data-theme="dark"] .fb__filter-btn--active { color: #93c5fd; }
</style>
