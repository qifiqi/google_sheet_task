<template>
  <div class="layout-container">
    <!-- 顶部导航栏 -->
    <el-header class="layout-header" height="60px">
      <div class="header-content">
        <div class="header-left">
          <el-button 
            :icon="Fold" 
            text 
            @click="toggleSidebar"
            class="sidebar-toggle"
          />
          <h1 class="system-title">Google Sheet 任务管理系统</h1>
        </div>
        <div class="header-right">
          <el-dropdown>
            <el-button :icon="Setting" circle />
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="$router.push('/admin/config')">
                  <el-icon><Setting /></el-icon>
                  系统配置
                </el-dropdown-item>
                <el-dropdown-item @click="refreshPage">
                  <el-icon><Refresh /></el-icon>
                  刷新页面
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </el-header>

    <el-container class="layout-main">
      <!-- 侧边栏 -->
      <el-aside 
        class="layout-sidebar" 
        :width="sidebarCollapsed ? '64px' : '240px'"
      >
        <div class="sidebar-content">
          <el-menu
            :default-active="$route.path"
            class="sidebar-menu"
            :collapse="sidebarCollapsed"
            router
          >
            <el-menu-item index="/admin/dashboard">
              <el-icon><Odometer /></el-icon>
              <template #title>仪表盘</template>
            </el-menu-item>
            
            <el-menu-item index="/admin/tasks">
              <el-icon><List /></el-icon>
              <template #title>任务管理</template>
            </el-menu-item>
            
            <el-menu-item index="/admin/config">
              <el-icon><Setting /></el-icon>
              <template #title>系统配置</template>
            </el-menu-item>
            
            <el-menu-item index="/admin/logs">
              <el-icon><Document /></el-icon>
              <template #title>系统日志</template>
            </el-menu-item>
            
            <el-divider />
            
            <el-menu-item index="/google-sheet/index">
              <el-icon><Grid /></el-icon>
              <template #title>Google Sheet</template>
            </el-menu-item>
          </el-menu>
        </div>
      </el-aside>

      <!-- 主内容区域 -->
      <el-main class="layout-content">
        <router-view />
      </el-main>
    </el-container>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAppStore } from '../stores'
import { 
  Fold, 
  Setting, 
  Refresh, 
  Odometer, 
  List, 
  Document, 
  Grid 
} from '@element-plus/icons-vue'

const appStore = useAppStore()

const sidebarCollapsed = computed(() => appStore.sidebarCollapsed)

const toggleSidebar = () => {
  appStore.toggleSidebar()
}

const refreshPage = () => {
  location.reload()
}
</script>

<style scoped>
.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 100%;
  padding: 0 20px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.system-title {
  font-size: 18px;
  font-weight: 500;
  color: var(--text-color-primary);
  margin: 0;
}

.sidebar-toggle {
  font-size: 18px;
}

.sidebar-content {
  height: 100%;
  padding: 16px 0;
}

.sidebar-menu {
  border-right: none;
  height: 100%;
}

.sidebar-menu .el-menu-item {
  height: 48px;
  line-height: 48px;
  margin: 4px 12px;
  border-radius: 6px;
}

.sidebar-menu .el-menu-item:hover {
  background-color: var(--el-color-primary-light-9);
}

.sidebar-menu .el-menu-item.is-active {
  background-color: var(--el-color-primary);
  color: white;
}

.sidebar-menu .el-menu-item.is-active:hover {
  background-color: var(--el-color-primary-dark-2);
}

.el-divider {
  margin: 12px 16px;
}
</style>
