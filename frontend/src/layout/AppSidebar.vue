<template>
  <el-menu
    :default-active="activeIndex"
    :collapse="collapsed"
    background-color="transparent"
    text-color="#c3d2f0"
    active-text-color="#ffffff"
    router
    class="app-sidebar"
  >
    <template v-for="item in nav" :key="item.key">
      <el-menu-item v-if="item.path" :index="item.path">
        <span>{{ item.label }}</span>
      </el-menu-item>

      <el-sub-menu v-else :index="item.key">
        <template #title>
          <span>{{ item.label }}</span>
        </template>
        <el-menu-item
          v-for="child in item.children"
          :key="child.key"
          :index="child.path"
        >
          {{ child.label }}
        </el-menu-item>
      </el-sub-menu>
    </template>
  </el-menu>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getNav } from '@/api/meta'

defineProps({ collapsed: Boolean })

const route = useRoute()
const nav = ref([])

const activeIndex = computed(() => {
  const queryString = new URLSearchParams(route.query).toString()
  return queryString ? `${route.path}?${queryString}` : route.path
})

onMounted(async () => {
  try {
    const res = await getNav()
    nav.value = res.data
  } catch {
    nav.value = []
  }
})
</script>

<style scoped>
.app-sidebar {
  height: 100%;
  border-right: none;
  font-size: 18px;
  padding: 12px 10px 10px;
}

.app-sidebar:not(.el-menu--collapse) {
  width: 240px;
}

.app-sidebar :deep(.el-menu-item),
.app-sidebar :deep(.el-sub-menu__title) {
  height: 52px;
  line-height: 52px;
  font-size: 18px;
  font-weight: 600;
  border-radius: 14px;
  margin-bottom: 6px;
  color: #c8d6ef !important;
  transition: background-color 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.app-sidebar :deep(.el-menu-item:hover),
.app-sidebar :deep(.el-sub-menu__title:hover) {
  background: rgba(255, 255, 255, 0.08) !important;
  color: #ffffff !important;
  transform: translateX(2px);
}

.app-sidebar :deep(.el-menu-item.is-active) {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.28), rgba(245, 158, 11, 0.22)) !important;
  color: #ffffff !important;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
}

.app-sidebar :deep(.el-sub-menu.is-active > .el-sub-menu__title) {
  color: #fff !important;
}

.app-sidebar :deep(.el-menu) {
  border-right: none;
  background: transparent;
}

@media (max-width: 767px) {
  .app-sidebar {
    font-size: 14px;
    padding-top: 4px;
  }

  .app-sidebar :deep(.el-menu-item),
  .app-sidebar :deep(.el-sub-menu__title) {
    height: 44px;
    line-height: 44px;
    font-size: 14px;
  }
}
</style>
