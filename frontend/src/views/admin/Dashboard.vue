<template>
  <div class="dashboard">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="title">仪表盘</h1>
      <p class="description">系统运行状态总览</p>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card">
          <div class="stat-content">
            <div class="stat-info">
              <div class="stat-number">{{ stats.totalTasks }}</div>
              <div class="stat-label">总任务数</div>
            </div>
            <div class="stat-icon">
              <el-icon><List /></el-icon>
            </div>
          </div>
        </div>
      </el-col>
      
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card success">
          <div class="stat-content">
            <div class="stat-info">
              <div class="stat-number">{{ stats.completedTasks }}</div>
              <div class="stat-label">已完成</div>
            </div>
            <div class="stat-icon">
              <el-icon><CircleCheck /></el-icon>
            </div>
          </div>
        </div>
      </el-col>
      
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card warning">
          <div class="stat-content">
            <div class="stat-info">
              <div class="stat-number">{{ stats.runningTasks }}</div>
              <div class="stat-label">执行中</div>
            </div>
            <div class="stat-icon">
              <el-icon><VideoPlay /></el-icon>
            </div>
          </div>
        </div>
      </el-col>
      
      <el-col :xs="24" :sm="12" :md="6">
        <div class="stat-card danger">
          <div class="stat-content">
            <div class="stat-info">
              <div class="stat-number">{{ stats.errorTasks }}</div>
              <div class="stat-label">执行出错</div>
            </div>
            <div class="stat-icon">
              <el-icon><WarningFilled /></el-icon>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 最近任务 -->
    <el-card class="recent-tasks-card">
      <template #header>
        <div class="card-header">
          <span class="title">
            <el-icon><Clock /></el-icon>
            最近任务
          </span>
          <el-button 
            type="primary" 
            size="small" 
            @click="refreshTasks"
            :loading="loading"
          >
            刷新
          </el-button>
        </div>
      </template>
      
      <div class="table-container">
        <el-table 
          :data="recentTasks" 
          v-loading="loading"
          empty-text="暂无任务数据"
        >
          <el-table-column prop="name" label="任务名称" min-width="150" />
          <el-table-column prop="task_type" label="类型" width="120">
            <template #default="{ row }">
              <el-tag size="small">{{ row.task_type }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag 
                :type="getTaskStatus(row.status).type" 
                size="small"
              >
                {{ getTaskStatus(row.status).text }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" width="150">
            <template #default="{ row }">
              <div v-if="row.total_steps > 0">
                <el-progress 
                  :percentage="Math.round((row.current_step / row.total_steps) * 100)"
                  :stroke-width="8"
                  :show-text="false"
                />
                <div class="progress-text">
                  {{ row.current_step }}/{{ row.total_steps }}
                </div>
              </div>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="160">
            <template #default="{ row }">
              {{ formatTime(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button 
                type="primary" 
                size="small" 
                text
                @click="viewTask(row.id)"
              >
                查看
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 快速操作和系统信息 -->
    <el-row :gutter="20">
      <el-col :xs="24" :md="12">
        <el-card class="quick-actions-card">
          <template #header>
            <span class="title">
              <el-icon><Lightning /></el-icon>
              快速操作
            </span>
          </template>
          
          <div class="quick-actions">
            <el-button 
              type="primary" 
              size="large" 
              @click="$router.push('/google-sheet/create')"
              class="action-button"
            >
              <el-icon><Plus /></el-icon>
              创建Google Sheet任务
            </el-button>
            
            <el-button 
              size="large" 
              @click="$router.push('/admin/tasks')"
              class="action-button"
            >
              <el-icon><List /></el-icon>
              查看所有任务
            </el-button>
            
            <el-button 
              size="large" 
              @click="$router.push('/admin/config')"
              class="action-button"
            >
              <el-icon><Setting /></el-icon>
              系统配置
            </el-button>
          </div>
        </el-card>
      </el-col>
      
      <el-col :xs="24" :md="12">
        <el-card class="system-info-card">
          <template #header>
            <span class="title">
              <el-icon><InfoFilled /></el-icon>
              系统信息
            </span>
          </template>
          
          <div class="system-info">
            <div class="info-item">
              <span class="label">系统版本:</span>
              <span class="value">v2.0.0</span>
            </div>
            <div class="info-item">
              <span class="label">运行状态:</span>
              <el-tag type="success" size="small">正常</el-tag>
            </div>
            <div class="info-item">
              <span class="label">最后更新:</span>
              <span class="value">{{ formatTime(new Date()) }}</span>
            </div>
            <div class="info-item">
              <span class="label">前端框架:</span>
              <span class="value">Vue 3 + Element Plus</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useTaskStore } from '../../stores'
import { formatTime, getTaskStatus } from '../../utils'
import { 
  List, 
  CircleCheck, 
  VideoPlay, 
  WarningFilled, 
  Clock, 
  Lightning, 
  Plus, 
  Setting, 
  InfoFilled 
} from '@element-plus/icons-vue'

const router = useRouter()
const taskStore = useTaskStore()

const loading = ref(false)
const stats = ref({
  totalTasks: 0,
  completedTasks: 0,
  runningTasks: 0,
  errorTasks: 0
})
const recentTasks = ref([])

// 刷新任务数据
const refreshTasks = async () => {
  loading.value = true
  try {
    await taskStore.fetchTasks()
    updateStats()
    updateRecentTasks()
  } catch (error) {
    console.error('刷新任务失败:', error)
  } finally {
    loading.value = false
  }
}

// 更新统计数据
const updateStats = () => {
  const tasks = taskStore.tasks
  stats.value = {
    totalTasks: tasks.length,
    completedTasks: tasks.filter(task => task.status === 'completed').length,
    runningTasks: tasks.filter(task => task.status === 'running').length,
    errorTasks: tasks.filter(task => task.status === 'error').length
  }
}

// 更新最近任务
const updateRecentTasks = () => {
  const tasks = [...taskStore.tasks]
  tasks.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  recentTasks.value = tasks.slice(0, 10)
}

// 查看任务详情
const viewTask = (taskId) => {
  router.push(`/google-sheet/detail?task_id=${taskId}`)
}

// 页面加载时获取数据
onMounted(() => {
  refreshTasks()
  
  // 设置定时刷新
  const interval = setInterval(refreshTasks, 30000) // 30秒刷新一次
  
  // 组件卸载时清除定时器
  onBeforeUnmount(() => {
    clearInterval(interval)
  })
})
</script>

<style scoped>
.dashboard {
  padding: 0;
}

.stats-row {
  margin-bottom: 24px;
}

.stat-card {
  background: linear-gradient(135deg, var(--el-color-primary) 0%, var(--el-color-primary-dark-2) 100%);
  color: white;
  border-radius: 8px;
  padding: 24px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  margin-bottom: 16px;
}

.stat-card.success {
  background: linear-gradient(135deg, var(--el-color-success) 0%, var(--el-color-success-dark-2) 100%);
}

.stat-card.warning {
  background: linear-gradient(135deg, var(--el-color-warning) 0%, var(--el-color-warning-dark-2) 100%);
}

.stat-card.danger {
  background: linear-gradient(135deg, var(--el-color-danger) 0%, var(--el-color-danger-dark-2) 100%);
}

.stat-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat-number {
  font-size: 32px;
  font-weight: bold;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 14px;
  opacity: 0.9;
}

.stat-icon {
  font-size: 48px;
  opacity: 0.8;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header .title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}

.progress-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: center;
  margin-top: 4px;
}

.text-muted {
  color: var(--el-text-color-placeholder);
}

.quick-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.action-button {
  width: 100%;
  height: 48px;
  justify-content: flex-start;
}

.system-info {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.info-item .label {
  font-weight: 500;
  color: var(--el-text-color-regular);
}

.info-item .value {
  color: var(--el-text-color-primary);
}

.recent-tasks-card,
.quick-actions-card,
.system-info-card {
  margin-bottom: 20px;
}

@media (max-width: 768px) {
  .stat-content {
    flex-direction: column;
    text-align: center;
    gap: 12px;
  }
  
  .stat-icon {
    font-size: 36px;
  }
  
  .stat-number {
    font-size: 24px;
  }
}
</style>
