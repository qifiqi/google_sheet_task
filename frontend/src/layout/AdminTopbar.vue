<script setup lang="ts">
import {
  Bell,
  FullScreen,
  Grid,
  Menu,
  Moon,
  Refresh,
  Search,
  Setting,
  SwitchButton,
} from '@element-plus/icons-vue'
import type { CurrentUser } from '../types/api'

defineProps<{
  user: CurrentUser | null
  roleText: string
}>()

const emit = defineEmits<{
  toggleSidebar: []
  logout: []
}>()
</script>

<template>
  <header class="admin-topbar">
    <div class="admin-topbar__left">
      <el-button :icon="Menu" text class="admin-icon-button" @click="emit('toggleSidebar')" />
      <el-button :icon="Refresh" text class="admin-icon-button" />
      <el-button :icon="Grid" text class="admin-icon-button" />
      <el-breadcrumb separator="/" class="admin-topbar__breadcrumb">
        <el-breadcrumb-item>仪表盘</el-breadcrumb-item>
        <el-breadcrumb-item>工作台</el-breadcrumb-item>
      </el-breadcrumb>
    </div>

    <div class="admin-topbar__right">
      <el-input class="admin-topbar__search" placeholder="搜索" :prefix-icon="Search">
        <template #suffix>
          <span class="admin-topbar__kbd">ctrl k</span>
        </template>
      </el-input>
      <el-button :icon="FullScreen" text class="admin-icon-button" />
      <el-button :icon="Moon" text class="admin-icon-button" />
      <el-badge is-dot class="admin-topbar__badge">
        <el-button :icon="Bell" text class="admin-icon-button" />
      </el-badge>
      <el-button :icon="Setting" text class="admin-icon-button" />
      <el-dropdown trigger="click">
        <button class="admin-topbar__user" type="button">
          <span class="admin-topbar__avatar">{{ user?.username?.slice(0, 2).toUpperCase() || 'JA' }}</span>
          <span class="admin-topbar__user-text">
            <strong>{{ user?.username || '未登录' }}</strong>
            <small>{{ roleText }}</small>
          </span>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>{{ roleText }}</el-dropdown-item>
            <el-dropdown-item divided :icon="SwitchButton" @click="emit('logout')">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>
</template>

<style scoped>
.admin-topbar {
  height: var(--admin-header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 22px;
  background: var(--admin-header-bg);
  border-bottom: 1px solid var(--admin-border);
}

.admin-topbar__left,
.admin-topbar__right {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.admin-topbar__breadcrumb {
  margin-left: 14px;
}

.admin-topbar__search {
  width: 162px;
}

.admin-topbar__kbd {
  padding: 1px 7px;
  border: 1px solid var(--admin-primary-border);
  border-radius: 4px;
  color: var(--admin-primary);
  font-size: 11px;
  line-height: 1.2;
}

.admin-icon-button {
  width: 32px;
  height: 32px;
  color: var(--admin-text-muted);
}

.admin-topbar__badge {
  height: 32px;
}

.admin-topbar__user {
  height: 36px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  background: var(--admin-surface);
  color: var(--admin-text);
  cursor: pointer;
}

.admin-topbar__avatar {
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--admin-primary), #10b981);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}

.admin-topbar__user-text {
  display: grid;
  text-align: left;
  line-height: 1.1;
}

.admin-topbar__user-text strong {
  max-width: 90px;
  overflow: hidden;
  color: var(--admin-text);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admin-topbar__user-text small {
  max-width: 90px;
  overflow: hidden;
  color: var(--admin-text-placeholder);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 980px) {
  .admin-topbar__breadcrumb,
  .admin-topbar__search,
  .admin-topbar__user-text {
    display: none;
  }
}
</style>
