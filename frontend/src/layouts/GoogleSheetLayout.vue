<template>
  <div class="layout-container">
    <!-- 顶部导航栏 -->
    <el-header class="layout-header" height="60px">
      <div class="header-content">
        <div class="header-left">
          <el-button 
            :icon="ArrowLeft" 
            text 
            @click="$router.push('/admin')"
            class="back-button"
          >
            返回管理面板
          </el-button>
          <h1 class="system-title">Google Sheet 管理</h1>
        </div>
        <div class="header-right">
          <el-button 
            type="primary" 
            :icon="Plus"
            @click="$router.push('/google-sheet/create')"
          >
            创建任务
          </el-button>
        </div>
      </div>
    </el-header>

    <el-container class="layout-main">
      <!-- 侧边栏 -->
      <el-aside class="layout-sidebar" width="240px">
        <div class="sidebar-content">
          <el-menu
            :default-active="$route.path"
            class="sidebar-menu"
            router
          >
            <el-menu-item index="/google-sheet/index">
              <el-icon><List /></el-icon>
              <template #title>任务列表</template>
            </el-menu-item>
            
            <el-menu-item index="/google-sheet/create">
              <el-icon><Plus /></el-icon>
              <template #title>创建任务</template>
            </el-menu-item>
            
            <el-divider />
            
            <el-menu-item index="/admin/dashboard">
              <el-icon><Odometer /></el-icon>
              <template #title>返回仪表盘</template>
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
import { 
  ArrowLeft, 
  Plus, 
  List, 
  Odometer 
} from '@element-plus/icons-vue'
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

.back-button {
  font-size: 14px;
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
