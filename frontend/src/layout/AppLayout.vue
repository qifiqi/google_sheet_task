<template>
  <div class="app-layout" :class="{ 'sidebar-open': sidebarOpen }">
    <!-- Mobile overlay -->
    <div
      v-if="sidebarOpen && isMobile"
      class="app-layout__overlay"
      @click="sidebarOpen = false"
    />

    <!-- Sidebar -->
    <aside
      class="app-layout__sidebar"
      :class="{ 'is-mobile': isMobile, 'is-open': sidebarOpen }"
    >
      <div class="app-layout__sidebar-brand">
        <span class="brand-icon">
          <el-icon :size="18"><DataBoard /></el-icon>
        </span>
        <div class="brand-text">
          <div class="brand-text__title">Jaspil</div>
          <div class="brand-text__subtitle">任务管理平台</div>
        </div>
      </div>

      <div class="app-layout__sidebar-body">
        <SidebarMenu />
      </div>
    </aside>

    <!-- Main content -->
    <div class="app-layout__main" :style="mainStyle">
      <AppHeader @toggle-sidebar="sidebarOpen = !sidebarOpen" />

      <main class="app-layout__content">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { DataBoard } from '@element-plus/icons-vue'
import SidebarMenu from './components/SidebarMenu.vue'
import AppHeader from './components/AppHeader.vue'

const SIDEBAR_WIDTH = 240
const MOBILE_BREAKPOINT = 768

const sidebarOpen = ref(false)
const windowWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1200)
const isMobile = computed(() => windowWidth.value < MOBILE_BREAKPOINT)

const mainStyle = computed(() => {
  if (isMobile.value) return {}
  return { marginLeft: `${SIDEBAR_WIDTH}px` }
})

function handleResize() {
  windowWidth.value = window.innerWidth
  if (!isMobile.value) {
    sidebarOpen.value = false
  }
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
})
</script>

<style lang="scss" scoped>
.app-layout {
  min-height: 100vh;
  background: var(--app-bg);

  &__overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 999;
    animation: overlay-fade-in 0.2s ease;
  }

  &__sidebar {
    position: fixed;
    top: 0;
    bottom: 0;
    left: 0;
    width: 240px;
    background: var(--app-surface-sidebar);
    border-right: 1px solid var(--app-border);
    box-shadow: inset -1px 0 0 rgba(0, 0, 0, 0.03);
    display: flex;
    flex-direction: column;
    z-index: 1000;
    overflow: hidden;
    transition: transform var(--app-transition-slow);

    &.is-mobile {
      transform: translateX(-100%);

      &.is-open {
        transform: translateX(0);
        box-shadow: 4px 0 24px rgba(0, 0, 0, 0.15);
      }
    }
  }

  &__sidebar-brand {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px 18px;
    border-bottom: 1px solid var(--app-border-light);
    flex-shrink: 0;

    .brand-icon {
      width: 36px;
      height: 36px;
      border-radius: 10px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%);
      color: #fff;
      font-size: 16px;
      box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
      flex-shrink: 0;
    }

    .brand-text {
      min-width: 0;

      &__title {
        font-size: 15px;
        font-weight: 700;
        color: var(--app-text);
        letter-spacing: 0.04em;
      }

      &__subtitle {
        font-size: 11px;
        color: var(--app-text-subtle);
        letter-spacing: 0.02em;
      }
    }
  }

  &__sidebar-body {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    scrollbar-gutter: stable;

    &::-webkit-scrollbar {
      width: 5px;
    }
    &::-webkit-scrollbar-track {
      background: transparent;
    }
    &::-webkit-scrollbar-thumb {
      background: var(--app-border);
      border-radius: 3px;
    }
  }

  &__main {
    min-height: 100vh;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  &__content {
    flex: 1;
    padding: var(--app-page-padding);
    width: 100%;
    max-width: var(--app-content-max-width);
  }
}

@keyframes overlay-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
