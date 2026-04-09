<template>
  <el-container class="app-layout">
    <el-aside v-if="!isMobile" :width="collapsed ? '64px' : `${sidebarWidth}px`" class="app-aside">
      <div class="brand-shell" @click="collapsed = !collapsed">
        <div class="brand-mark">TP</div>
        <div v-show="!collapsed" class="brand-copy">
          <div class="brand-copy__title">Task Platform</div>
          <div class="brand-copy__subtitle">参数校验与任务编排</div>
        </div>
      </div>
      <AppSidebar :collapsed="collapsed" />
      <div v-if="!collapsed" class="aside-footer">
        <span class="aside-footer__dot"></span>
        数据通道在线
      </div>
    </el-aside>

    <el-drawer
      v-if="isMobile"
      v-model="drawerOpen"
      class="app-drawer"
      direction="ltr"
      :size="`${sidebarWidth}px`"
      :with-header="false"
    >
      <div class="brand-shell brand-shell--drawer">
        <div class="brand-mark">TP</div>
        <div class="brand-copy">
          <div class="brand-copy__title">Task Platform</div>
          <div class="brand-copy__subtitle">参数校验与任务编排</div>
        </div>
      </div>
      <AppSidebar :collapsed="false" />
    </el-drawer>

    <el-container class="main-container">
      <el-header class="app-header-wrap" :height="`${headerHeight}px`">
        <AppHeader :sidebar-open="drawerOpen" @toggle-sidebar="drawerOpen = !drawerOpen">
          <template #user>
            <el-dropdown v-if="user" @command="handleCommand">
              <span class="user-info el-dropdown-link">
                {{ user.username }}
                <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="logout">退出登录</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </AppHeader>
      </el-header>
      <el-main>
        <router-view :key="route.fullPath" />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown } from '@element-plus/icons-vue'
import { useResponsive } from '@/composables/useResponsive'
import { useAuth } from '@/composables/useAuth'
import AppSidebar from './AppSidebar.vue'
import AppHeader from './AppHeader.vue'

const { isMobile, sidebarWidth, headerHeight } = useResponsive()
const { user, fetchUser, logout } = useAuth()
const route = useRoute()
const router = useRouter()
const collapsed = ref(false)
const drawerOpen = ref(false)

onMounted(async () => {
  if (!user.value) {
    await fetchUser()
  }
})

function handleCommand(command) {
  if (command === 'logout') {
    logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.app-layout {
  height: 100vh;
  background: transparent;
}

.app-aside {
  display: flex;
  flex-direction: column;
  background: var(--app-sidebar-bg);
  transition: width 0.3s;
  overflow: hidden;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 12px 0 32px rgba(9, 18, 39, 0.14);
}

.brand-shell {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 18px 16px;
  color: #fff;
  cursor: pointer;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0));
}

.brand-shell--drawer {
  padding-inline: 8px 4px;
  margin-bottom: 10px;
  border-bottom: none;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 14px;
  background: linear-gradient(135deg, #f59e0b 0%, #facc15 100%);
  color: #11203f;
  font-family: 'Fira Code', monospace;
  font-weight: 700;
  box-shadow: 0 12px 24px rgba(245, 158, 11, 0.24);
}

.brand-copy__title {
  font-weight: 700;
  letter-spacing: 0.01em;
}

.brand-copy__subtitle {
  margin-top: 2px;
  color: rgba(255, 255, 255, 0.64);
}

.aside-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: auto 14px 14px;
  padding: 12px 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  color: rgba(255, 255, 255, 0.7);
  background: rgba(255, 255, 255, 0.04);
}

.aside-footer__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 5px rgba(34, 197, 94, 0.16);
  animation: sidebarPulse 2.4s infinite;
}

.app-header-wrap {
  padding: 0;
}

.main-container {
  overflow: hidden;
}

.user-info {
  cursor: pointer;
  color: var(--app-text);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  border: 1px solid var(--app-border);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
}

.app-drawer :deep(.el-drawer) {
  background: linear-gradient(180deg, #102146 0%, #183569 100%);
}

@keyframes sidebarPulse {
  0%,
  100% {
    transform: scale(1);
  }

  50% {
    transform: scale(1.15);
  }
}

@media (max-width: 767px) {
  .brand-shell {
    padding: 12px 0 14px;
  }

  .brand-mark {
    width: 38px;
    height: 38px;
  }
}
</style>
