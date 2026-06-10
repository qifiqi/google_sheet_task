<template>
  <header class="app-header">
    <div class="app-header__left">
      <el-button
        class="app-header__menu-btn hide-desktop"
        text
        @click="$emit('toggle-sidebar')"
      >
        <el-icon :size="20"><Fold /></el-icon>
      </el-button>

      <el-breadcrumb separator="/" class="app-header__breadcrumb">
        <el-breadcrumb-item :to="{ path: '/' }">
          <el-icon :size="14"><HomeFilled /></el-icon>
        </el-breadcrumb-item>
        <el-breadcrumb-item v-for="crumb in breadcrumbs" :key="crumb.path">
          {{ crumb.title }}
        </el-breadcrumb-item>
      </el-breadcrumb>
    </div>

    <div class="app-header__right">
      <el-switch
        :model-value="isDark"
        @update:model-value="applyTheme($event ? 'dark' : 'light')"
        inline-prompt
        :active-icon="Moon"
        :inactive-icon="Sunny"
        class="app-header__theme-switch"
      />

      <el-dropdown trigger="click" @command="handleCommand">
        <button class="app-header__user-btn">
          <span class="app-header__avatar">{{ userInitial }}</span>
          <span class="app-header__username hide-mobile">{{ username }}</span>
          <el-icon class="hide-mobile"><ArrowDown /></el-icon>
        </button>

        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>
              <span class="text-muted">{{ userRole }}</span>
            </el-dropdown-item>
            <el-dropdown-item divided command="logout">
              <el-icon><SwitchButton /></el-icon>
              退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Fold, HomeFilled, ArrowDown, Moon, Sunny, SwitchButton } from '@element-plus/icons-vue'
import { useAuth } from '@/composables/useAuth'
import { useTheme } from '@/composables/useTheme'

defineEmits(['toggle-sidebar'])

const route = useRoute()
const router = useRouter()
const { user, logout } = useAuth()
const { isDark, applyTheme } = useTheme()

const username = computed(() => user.value?.username ?? '用户')
const userRole = computed(() => user.value?.role?.name ?? '成员')
const userInitial = computed(() => (username.value || 'U').charAt(0).toUpperCase())

const breadcrumbs = computed(() => {
  const matched = route.matched.filter((r) => r.meta?.title)
  return matched.map((r) => ({
    path: r.path,
    title: r.meta.title,
  }))
})

async function handleCommand(cmd) {
  if (cmd === 'logout') {
    await logout()
    router.push('/login')
  }
}
</script>

<style lang="scss" scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--app-header-height);
  padding: 0 20px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--app-border);
  position: sticky;
  top: 0;
  z-index: 100;

  &__left {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 0;
  }

  &__right {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-shrink: 0;
  }

  &__menu-btn {
    padding: 6px;
  }

  &__breadcrumb {
    white-space: nowrap;
    overflow: hidden;
  }

  &__theme-switch {
    --el-switch-on-color: #1e293b;
    --el-switch-off-color: #fbbf24;
  }

  &__user-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    border: none;
    background: transparent;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: var(--app-radius-full);
    transition: background var(--app-transition-fast);
    color: var(--app-text);

    &:hover {
      background: var(--app-surface-elevated);
    }
  }

  &__avatar {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-weight: 700;
    font-size: 14px;
    background: linear-gradient(135deg, #fb7185 0%, #8b5cf6 100%);
    flex-shrink: 0;
  }

  &__username {
    font-size: 13.5px;
    font-weight: 500;
  }
}

.hide-desktop {
  @media (min-width: 768px) {
    display: none !important;
  }
}
</style>
