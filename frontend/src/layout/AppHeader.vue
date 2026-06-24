<template>
  <div class="app-header">
    <div class="app-header__left">
      <el-icon v-if="isMobile" class="hamburger" @click="$emit('toggle-sidebar')">
        <Fold v-if="!sidebarOpen" />
        <Expand v-else />
      </el-icon>

      <div class="app-header__title-wrap">
        <span class="app-header__title">{{ currentTitle }}</span>
      </div>
    </div>

    <el-breadcrumb separator="/" class="app-header__breadcrumb">
      <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
      <el-breadcrumb-item v-if="currentTitle">{{ currentTitle }}</el-breadcrumb-item>
    </el-breadcrumb>

    <div class="header-right">
      <el-switch
        v-model="switchValue"
        class="theme-switch"
        :active-action-icon="Moon"
        :inactive-action-icon="Sunny"
        inline-prompt
      />
      <slot name="user" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Expand, Fold, Moon, Sunny } from '@element-plus/icons-vue'
import { useResponsive } from '@/composables/useResponsive'
import { useTheme } from '@/composables/useTheme'

defineProps({ sidebarOpen: Boolean })
defineEmits(['toggle-sidebar'])

const route = useRoute()
const { isMobile, headerHeight } = useResponsive()
const { switchValue } = useTheme()
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
  border-bottom: 1px solid var(--app-header-border);
  background: var(--app-header-bg);
  backdrop-filter: blur(20px);
}

.app-header__left {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.app-header__title-wrap {
  min-width: 0;
}

.app-header__title {
  display: block;
  overflow: hidden;
  color: var(--app-text);
  font-size: 18px;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  text-overflow: ellipsis;
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
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: auto;
}

.theme-switch :deep(.el-switch__core) {
  --el-switch-on-color: var(--app-primary);
  --el-switch-off-color: var(--app-surface-elevated);
  border: 1px solid var(--app-border);
}

.theme-switch :deep(.el-switch__action) {
  color: var(--app-text);
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

  .app-header__title {
    font-size: 16px;
  }
}
</style>
