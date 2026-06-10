<template>
  <li v-if="visible" class="sidebar-menu-item">
    <!-- Group with children -->
    <template v-if="item.children?.length">
      <button
        class="sidebar-group-toggle"
        :class="{ 'is-active': isGroupActive }"
        @click="toggleGroup"
      >
        <span class="sidebar-group-toggle__label">{{ item.label }}</span>
        <el-icon class="sidebar-group-toggle__icon" :class="{ 'is-open': isExpanded }">
          <ArrowRight />
        </el-icon>
      </button>

      <el-collapse-transition>
        <ul v-show="isExpanded" class="sidebar-submenu">
          <SidebarMenuItem
            v-for="child in item.children"
            :key="child.key"
            :item="child"
          />
        </ul>
      </el-collapse-transition>
    </template>

    <!-- Leaf item -->
    <router-link
      v-else-if="item.path"
      :to="normalizedPath"
      class="sidebar-nav-link"
      :class="{ 'is-active': isActive }"
    >
      <el-icon v-if="iconComponent" class="sidebar-nav-link__icon">
        <component :is="iconComponent" />
      </el-icon>
      <span class="sidebar-nav-link__label">{{ item.label }}</span>
    </router-link>
  </li>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'

const props = defineProps({
  item: { type: Object, required: true },
})

const route = useRoute()

const ICON_MAP = {
  dashboard: 'Odometer',
  task: 'List',
  tasks: 'Tickets',
  templates: 'Document',
  results: 'DataAnalysis',
  data: 'Coin',
  model_summary: 'TrendCharts',
  scheduler_group: 'Timer',
  scheduler: 'AlarmClock',
  system: 'Setting',
  config: 'Tools',
  sheets: 'Grid',
  navigation: 'Menu',
  logs: 'Notebook',
  users: 'User',
  roles: 'Lock',
  business: 'Briefcase',
  c3: 'Document',
  c4: 'Document',
  c5: 'Document',
  backtest: 'DataLine',
  backtest_multi_product: 'PieChart',
  xpl: 'Histogram',
  xpl_v1: 'DataBoard',
}

const iconComponent = computed(() => {
  const name = ICON_MAP[props.item.key]
  if (!name) return null
  return name
})

const visible = computed(() => {
  // Nav items are already filtered by permission from the API
  // Groups are visible if they have visible children
  if (props.item.children?.length) return true
  // Leaf items are always visible (permission checked at route level)
  return true
})

const normalizedPath = computed(() => {
  if (!props.item.path) return '#'
  return props.item.path
})

const isActive = computed(() => {
  return route.path === normalizedPath.value
})

// Group expand state
const isGroupActive = computed(() => {
  if (!props.item.children?.length) return false
  return props.item.children.some((child) => {
    if (child.path) return route.path === child.path
    if (child.children?.length) {
      return child.children.some((gc) => gc.path && route.path === gc.path)
    }
    return false
  })
})

const isExpanded = ref(isGroupActive.value)

watch(isGroupActive, (val) => {
  if (val) isExpanded.value = true
})

function toggleGroup() {
  isExpanded.value = !isExpanded.value
}
</script>

<style lang="scss" scoped>
.sidebar-menu-item {
  list-style: none;
}

.sidebar-group-toggle {
  width: 100%;
  border: none;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--sidebar-group-color);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 14px 14px 8px;
  border-radius: 10px;
  cursor: pointer;
  transition: background-color var(--app-transition-fast), color var(--app-transition-fast);

  &:hover {
    background: var(--sidebar-group-hover-bg);
    color: var(--sidebar-nav-hover-color);
  }

  &__icon {
    font-size: 12px;
    color: var(--app-text-subtle);
    transition: transform var(--app-transition-base), color var(--app-transition-base);

    &.is-open {
      transform: rotate(90deg);
      color: var(--app-primary);
    }
  }
}

.sidebar-submenu {
  list-style: none;
  padding: 2px 0 2px 4px;
  margin: 0;
}

.sidebar-nav-link {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--sidebar-nav-color);
  padding: 9px 12px;
  border-radius: 10px;
  margin-bottom: 2px;
  font-weight: 500;
  font-size: 13.5px;
  text-decoration: none;
  transition: all 0.18s ease;

  &:hover {
    color: var(--sidebar-nav-hover-color);
    background: var(--sidebar-nav-hover-bg);
  }

  &.is-active {
    color: var(--sidebar-nav-active-color);
    background: var(--sidebar-nav-active-bg);
    box-shadow: inset 0 0 0 1px rgba(37, 99, 235, 0.12);
  }

  &__icon {
    font-size: 15px;
    opacity: 0.85;
    flex-shrink: 0;
  }

  &__label {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
</style>
