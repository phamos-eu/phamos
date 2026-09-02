<script setup>
import { ref, computed, onBeforeUnmount } from "vue";

const props = defineProps({
  search: String,
  statusFilter: Array,
  sourceFilter: Array,
  ownerFilter: Array,
  sortBy: String,
  sortDir: String,
  statusOptions: Array,
  sourceOptions: Array,
  ownerOptions: Array,
  resultCount: Number,
  totalCount: Number,
});

const emit = defineEmits([
  "update:search", "update:statusFilter", "update:sourceFilter",
  "update:ownerFilter", "update:sortBy", "update:sortDir", "clear-all",
]);

const activeDropdown = ref(null);
const statusSearch = ref("");
const sourceSearch = ref("");
const ownerSearch = ref("");

const SORT_OPTIONS = [
  { value: "modified:desc", label: "Recently modified", dir: "desc" },
  { value: "modified:asc",  label: "Oldest modified",   dir: "asc" },
  { value: "lead_name:asc", label: "Name A–Z",           dir: "asc" },
  { value: "company:asc",   label: "Company A–Z",        dir: "asc" },
  { value: "status:asc",    label: "Status",             dir: "asc" },
];

const sortKey = computed(() => `${props.sortBy}:${props.sortDir}`);
const activeSortLabel = computed(() => SORT_OPTIONS.find(o => o.value === sortKey.value)?.label || "Sort");

const filteredStatusOptions = computed(() => {
  const q = statusSearch.value.trim().toLowerCase();
  return q ? (props.statusOptions || []).filter(s => s.toLowerCase().includes(q)) : (props.statusOptions || []);
});
const filteredSourceOptions = computed(() => {
  const q = sourceSearch.value.trim().toLowerCase();
  return q ? (props.sourceOptions || []).filter(s => s.toLowerCase().includes(q)) : (props.sourceOptions || []);
});
const filteredOwnerOptions = computed(() => {
  const q = ownerSearch.value.trim().toLowerCase();
  return q ? (props.ownerOptions || []).filter(o => o.toLowerCase().includes(q)) : (props.ownerOptions || []);
});

const hasActiveFilters = computed(() =>
  props.search ||
  props.statusFilter?.length ||
  props.sourceFilter?.length ||
  props.ownerFilter?.length ||
  props.sortBy !== "modified" || props.sortDir !== "desc"
);

function toggleStatus(val) {
  const cur = props.statusFilter || [];
  emit("update:statusFilter", cur.includes(val) ? cur.filter(v => v !== val) : [...cur, val]);
}
function toggleSource(val) {
  const cur = props.sourceFilter || [];
  emit("update:sourceFilter", cur.includes(val) ? cur.filter(v => v !== val) : [...cur, val]);
}
function toggleOwner(val) {
  const cur = props.ownerFilter || [];
  emit("update:ownerFilter", cur.includes(val) ? cur.filter(v => v !== val) : [...cur, val]);
}

function setSort(opt) {
  emit("update:sortBy", opt.value.split(":")[0]);
  emit("update:sortDir", opt.dir);
  closeDropdown();
}

function toggleDropdown(key) {
  activeDropdown.value = activeDropdown.value === key ? null : key;
}
function closeDropdown() { activeDropdown.value = null; }

function onClickOutside(e) {
  if (!e.target.closest(".fb__dropdown-wrap")) closeDropdown();
}

onBeforeUnmount(() => document.removeEventListener("click", onClickOutside));
</script>

<template>
  <div class="fb" @click.capture="$event._fbHandled || document.addEventListener('click', onClickOutside, { once: true })">
    <!-- Search -->
    <div class="fb__search">
      <svg class="fb__search-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>
      </svg>
      <input
        :value="search"
        type="text"
        class="fb__search-input"
        placeholder="Search leads…"
        @input="emit('update:search', $event.target.value)"
      />
      <button v-if="search" class="fb__clear-x" @click="emit('update:search', '')">×</button>
    </div>

    <!-- Filter chips row -->
    <div class="fb__chips">
      <!-- Status -->
      <div class="fb__dropdown-wrap">
        <button
          class="fb__chip"
          :class="{ 'fb__chip--active': statusFilter?.length }"
          @click.stop="toggleDropdown('status')"
        >
          Status{{ statusFilter?.length ? ` (${statusFilter.length})` : "" }}
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M7 10l5 5 5-5z"/></svg>
        </button>
        <div v-if="activeDropdown === 'status'" class="fb__dropdown">
          <input v-model="statusSearch" type="text" class="fb__dropdown-search" placeholder="Filter statuses…" />
          <div class="fb__dropdown-list">
            <label v-for="s in filteredStatusOptions" :key="s" class="fb__dropdown-item">
              <input type="checkbox" :checked="statusFilter?.includes(s)" @change="toggleStatus(s)" />
              {{ s }}
            </label>
          </div>
          <button v-if="statusFilter?.length" class="fb__dropdown-clear" @click="emit('update:statusFilter', [])">Clear</button>
        </div>
      </div>

      <!-- Source -->
      <div class="fb__dropdown-wrap">
        <button
          class="fb__chip"
          :class="{ 'fb__chip--active': sourceFilter?.length }"
          @click.stop="toggleDropdown('source')"
        >
          Source{{ sourceFilter?.length ? ` (${sourceFilter.length})` : "" }}
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M7 10l5 5 5-5z"/></svg>
        </button>
        <div v-if="activeDropdown === 'source'" class="fb__dropdown">
          <input v-model="sourceSearch" type="text" class="fb__dropdown-search" placeholder="Filter sources…" />
          <div class="fb__dropdown-list">
            <label v-for="s in filteredSourceOptions" :key="s" class="fb__dropdown-item">
              <input type="checkbox" :checked="sourceFilter?.includes(s)" @change="toggleSource(s)" />
              {{ s }}
            </label>
          </div>
          <button v-if="sourceFilter?.length" class="fb__dropdown-clear" @click="emit('update:sourceFilter', [])">Clear</button>
        </div>
      </div>

      <!-- Owner -->
      <div class="fb__dropdown-wrap">
        <button
          class="fb__chip"
          :class="{ 'fb__chip--active': ownerFilter?.length }"
          @click.stop="toggleDropdown('owner')"
        >
          Owner{{ ownerFilter?.length ? ` (${ownerFilter.length})` : "" }}
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M7 10l5 5 5-5z"/></svg>
        </button>
        <div v-if="activeDropdown === 'owner'" class="fb__dropdown">
          <input v-model="ownerSearch" type="text" class="fb__dropdown-search" placeholder="Filter owners…" />
          <div class="fb__dropdown-list">
            <label v-for="o in filteredOwnerOptions" :key="o" class="fb__dropdown-item">
              <input type="checkbox" :checked="ownerFilter?.includes(o)" @change="toggleOwner(o)" />
              {{ o }}
            </label>
          </div>
          <button v-if="ownerFilter?.length" class="fb__dropdown-clear" @click="emit('update:ownerFilter', [])">Clear</button>
        </div>
      </div>

      <!-- Sort -->
      <div class="fb__dropdown-wrap fb__dropdown-wrap--right">
        <button class="fb__chip" @click.stop="toggleDropdown('sort')">
          {{ activeSortLabel }}
          <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M7 10l5 5 5-5z"/></svg>
        </button>
        <div v-if="activeDropdown === 'sort'" class="fb__dropdown fb__dropdown--right">
          <button
            v-for="opt in SORT_OPTIONS" :key="opt.value"
            class="fb__dropdown-item fb__dropdown-item--btn"
            :class="{ 'fb__dropdown-item--sel': sortKey === opt.value }"
            @click="setSort(opt)"
          >{{ opt.label }}</button>
        </div>
      </div>

      <!-- Clear all -->
      <button v-if="hasActiveFilters" class="fb__chip fb__chip--danger" @click="emit('clear-all')">Clear all</button>

      <!-- Result count -->
      <span class="fb__count">{{ resultCount }} of {{ totalCount }}</span>
    </div>
  </div>
</template>

<style scoped>
.fb {
  display: flex; flex-direction: column; gap: 8px;
  padding: 10px 16px 8px;
  border-bottom: 1px solid var(--border-color);
  background: var(--card-bg);
  flex-shrink: 0;
  position: sticky; top: 0; z-index: 10;
}

/* Search */
.fb__search { position: relative; display: flex; align-items: center; }
.fb__search-icon { position: absolute; left: 10px; color: var(--text-muted); pointer-events: none; }
.fb__search-input {
  width: 100%; padding: 6px 32px 6px 30px;
  border: 1px solid var(--border-color); border-radius: 6px;
  background: var(--control-bg); color: var(--text-color);
  font-size: 13px; outline: none;
}
.fb__search-input:focus { border-color: var(--primary); }
.fb__clear-x { position: absolute; right: 8px; background: none; border: none; cursor: pointer; color: var(--text-muted); font-size: 16px; line-height: 1; padding: 0 2px; }

/* Chips row */
.fb__chips { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.fb__chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; border: 1px solid var(--border-color);
  border-radius: 20px; background: var(--control-bg);
  color: var(--text-muted); font-size: 12px; cursor: pointer;
  transition: border-color 0.1s, background 0.1s;
  white-space: nowrap;
}
.fb__chip:hover { border-color: var(--primary); color: var(--primary); }
.fb__chip--active { border-color: var(--primary); background: var(--primary-light); color: var(--primary); font-weight: 600; }
.fb__chip--danger { border-color: #ef4444; color: #ef4444; background: #fef2f2; }
.fb__chip--danger:hover { background: #fee2e2; }

.fb__count { font-size: 12px; color: var(--text-muted); margin-left: auto; }

/* Dropdown */
.fb__dropdown-wrap { position: relative; }
.fb__dropdown-wrap--right { margin-left: auto; }
.fb__dropdown {
  position: absolute; top: calc(100% + 4px); left: 0; z-index: 100;
  background: var(--card-bg); border: 1px solid var(--border-color);
  border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,.1);
  min-width: 180px; padding: 6px 0;
}
.fb__dropdown--right { left: auto; right: 0; }
.fb__dropdown-search {
  display: block; width: calc(100% - 16px); margin: 6px 8px;
  padding: 5px 8px; border: 1px solid var(--border-color);
  border-radius: 5px; font-size: 12px;
  background: var(--control-bg); color: var(--text-color);
}
.fb__dropdown-list { max-height: 200px; overflow-y: auto; }
.fb__dropdown-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 12px; font-size: 12.5px; color: var(--text-color);
  cursor: pointer;
}
.fb__dropdown-item:hover { background: var(--control-bg); }
.fb__dropdown-item--btn { border: none; background: transparent; width: 100%; text-align: left; }
.fb__dropdown-item--sel { font-weight: 700; color: var(--primary); }
.fb__dropdown-clear {
  display: block; width: calc(100% - 16px); margin: 4px 8px 2px;
  padding: 4px 8px; border: none; background: none;
  color: var(--danger); font-size: 12px; text-align: left; cursor: pointer;
}
.fb__dropdown-clear:hover { text-decoration: underline; }
</style>
