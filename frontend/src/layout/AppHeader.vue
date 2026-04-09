<template>
  <div class="app-header">
    <div class="app-header__left">
      <el-icon v-if="isMobile" class="hamburger" @click="$emit('toggle-sidebar')">
        <Fold v-if="!sidebarOpen" />
        <Expand v-else />
      </el-icon>

      <div class="app-header__status">
        <div class="app-header__eyebrow">Operations Console</div>
        <div class="app-header__status-row">
          <span class="app-header__product">Task Platform</span>
          <span class="app-header__live">
            <span class="app-header__live-dot"></span>
            实时同步
          </span>
        </div>
      </div>
    </div>

    <el-breadcrumb separator="/" class="app-header__breadcrumb">
      <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
      <el-breadcrumb-item v-if="currentTitle">{{ currentTitle }}</el-breadcrumb-item>
    </el-breadcrumb>

    <div class="header-right">
      <slot name="user" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Expand, Fold } from '@element-plus/icons-vue'
import { useResponsive } from '@/composables/useResponsive'

defineProps({ sidebarOpen: Boolean })
defineEmits(['toggle-sidebar'])

const route = useRoute()
const { isMobile, headerHeight } = useResponsive()
const currentTitle = computed(() => route.meta.title || '任务平台')
</script>

<style scoped>
.app-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 18px;
  height: v-bind('`${headerHeight}px`');
  padding: 10px 22px;
  border-bottom: 1px solid rgba(30, 64, 175, 0.08);
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(20px);
}

.app-header__left {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.app-header__status {
  min-width: 0;
}

.app-header__eyebrow {
  color: var(--app-text-muted);
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.app-header__status-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 4px;
}

.app-header__product {
  color: var(--app-text);
  font-weight: 700;
  line-height: 1;
}

.app-header__live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(34, 197, 94, 0.1);
  color: #15803d;
  font-weight: 600;
}

.app-header__live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 5px rgba(34, 197, 94, 0.16);
}

.app-header__breadcrumb {
  justify-self: end;
}

.hamburger {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  cursor: pointer;
  border-radius: 12px;
  background: var(--app-primary-soft);
  color: var(--app-primary);
}

.header-right {
  margin-left: auto;
}

@media (max-width: 1024px) {
  .app-header {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .app-header__breadcrumb {
    display: none;
  }
}

@media (max-width: 767px) {
  .app-header {
    padding: 10px 12px;
    gap: 12px;
  }

  .app-header__live {
    padding: 4px 8px;
  }
}
</style>
