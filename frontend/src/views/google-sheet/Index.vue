<template>
  <div class="google-sheet-index">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="title">Google Sheet 任务管理</h1>
      <p class="description">管理和监控Google Sheet参数批量校验任务</p>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索任务名称..."
          :prefix-icon="Search"
          clearable
          style="width: 300px"
          @input="handleSearch"
        />
        <el-select
          v-model="statusFilter"
          placeholder="状态筛选"
          clearable
          style="width: 150px"
          @change="handleFilter"
        >
          <el-option label="全部" value="" />
          <el-option label="待执行" value="pending" />
          <el-option label="执行中" value="running" />
          <el-option label="已完成" value="completed" />
          <el-option label="已取消" value="cancelled" />
          <el-option label="执行出错" value="error" />
        </el-select>
      </div>
      <div class="toolbar-right">
        <el-button 
          :icon="Refresh" 
          @click="refreshTasks"
          :loading="loading"
        >
          刷新
        </el-button>
        <el-button 
          type="primary" 
          :icon="Plus"
          @click="$router.push('/google-sheet/create')"
        >
          创建任务
        </el-button>
      </div>
    </div>

    <!-- 任务统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-content">
            <div class="stat-info">
              <div class="stat-number">{{ taskStats.total }}</div>
              <div class="stat-label">总任务数</div>
            </div>
            <div class="stat-icon">
              <el-icon><List /></el-icon>
            </div>
          </div>
        </div>
      </el-col>
      
      <el-col :xs="12" :sm="6">
        <div class="stat-card success">
          <div class="stat-content">
            <div class="stat-info">
              <div class="stat-number">{{ taskStats.completed }}</div>
              <div class="stat-label">已完成</div>
            </div>
            <div class="stat-icon">
              <el-icon><CircleCheck /></el-icon>
            </div>
          </div>
        </div>
      </el-col>
      
      <el-col :xs="12" :sm="6">
        <div class="stat-card warning">
          <div class="stat-content">
            <div class="stat-info">
              <div class="stat-number">{{ taskStats.running }}</div>
              <div class="stat-label">执行中</div>
            </div>
            <div class="stat-icon">
              <el-icon><VideoPlay /></el-icon>
            </div>
          </div>
        </div>
      </el-col>
      
      <el-col :xs="12" :sm="6">
        <div class="stat-card danger">
          <div class="stat-content">
            <div class="stat-info">
              <div class="stat-number">{{ taskStats.error }}</div>
              <div class="stat-label">执行出错</div>
            </div>
            <div class="stat-icon">
              <el-icon><WarningFilled /></el-icon>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 任务列表 -->
    <el-card class="task-list-card">
      <template #header>
        <div class="card-header">
          <span class="title">
            <el-icon><Grid /></el-icon>
            任务列表
          </span>
          <div class="header-actions">
            <el-switch
              v-model="autoRefresh"
              active-text="自动刷新"
              @change="toggleAutoRefresh"
            />
          </div>
        </div>
      </template>

      <div class="table-container">
        <el-table 
          :data="filteredTasks" 
          v-loading="loading"
          empty-text="暂无任务数据"
          @row-click="handleRowClick"
          class="task-table"
        >
          <el-table-column prop="name" label="任务名称" min-width="200">
            <template #default="{ row }">
              <div class="task-info">
                <div class="task-name">{{ row.name }}</div>
                <div class="task-description">{{ row.description }}</div>
              </div>
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
          
          <el-table-column label="进度" width="200">
            <template #default="{ row }">
              <div v-if="row.total_steps > 0" class="progress-container">
                <el-progress 
                  :percentage="Math.round((row.current_step / row.total_steps) * 100)"
                  :stroke-width="8"
                  :show-text="false"
                />
                <div class="progress-info">
                  <span class="progress-text">{{ row.current_step }}/{{ row.total_steps }}</span>
                  <span class="progress-percent">{{ Math.round((row.current_step / row.total_steps) * 100) }}%</span>
                </div>
              </div>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          
          <el-table-column label="配置信息" min-width="250">
            <template #default="{ row }">
              <div class="config-info">
                <div class="config-item">
                  <span class="label">表格ID:</span>
                  <span class="value">{{ getSheetId(row.config) }}</span>
                </div>
                <div class="config-item">
                  <span class="label">工作表:</span>
                  <span class="value">{{ getSheetName(row.config) }}</span>
                </div>
                <div class="config-item">
                  <span class="label">参数组合:</span>
                  <span class="value">{{ getParameterCount(row.config) }} 组</span>
                </div>
              </div>
            </template>
          </el-table-column>
          
          <el-table-column prop="created_at" label="创建时间" width="160">
            <template #default="{ row }">
              {{ formatTime(row.created_at) }}
            </template>
          </el-table-column>
          
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <div class="action-buttons">
                <el-button 
                  type="primary" 
                  size="small" 
                  text
                  @click.stop="viewTask(row.id)"
                >
                  查看详情
                </el-button>
                
                <el-button 
                  v-if="row.status === 'running'" 
                  type="warning" 
                  size="small" 
                  text
                  @click.stop="cancelTask(row.id)"
                >
                  取消
                </el-button>
                
                <el-button 
                  v-if="['error', 'cancelled'].includes(row.status)" 
                  type="success" 
                  size="small" 
                  text
                  @click.stop="restartTask(row.id)"
                >
                  重启
                </el-button>
                
                <el-dropdown @click.stop trigger="click">
                  <el-button size="small" text>
                    更多<el-icon class="el-icon--right"><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item @click="duplicateTask(row.id)">
                        <el-icon><CopyDocument /></el-icon>
                        复制任务
                      </el-dropdown-item>
                      <el-dropdown-item @click="exportTaskConfig(row.id)">
                        <el-icon><Download /></el-icon>
                        导出配置
                      </el-dropdown-item>
                      <el-dropdown-item divided @click="deleteTask(row.id)">
                        <el-icon><Delete /></el-icon>
                        删除任务
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 分页 -->
    <div class="pagination-container">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50, 100]"
        :total="totalTasks"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTaskStore } from '../../stores'
import { formatTime, getTaskStatus, debounce, downloadFile } from '../../utils'
import { 
  Search, 
  Refresh, 
  Plus, 
  List, 
  CircleCheck, 
  VideoPlay, 
  WarningFilled, 
  Grid,
  ArrowDown,
  CopyDocument,
  Download,
  Delete
} from '@element-plus/icons-vue'

const router = useRouter()
const taskStore = useTaskStore()

const loading = ref(false)
const autoRefresh = ref(false)
const searchKeyword = ref('')
const statusFilter = ref('')
const currentPage = ref(1)
const pageSize = ref(20)

let autoRefreshTimer = null

// 任务统计
const taskStats = computed(() => {
  const tasks = taskStore.tasks
  return {
    total: tasks.length,
    completed: tasks.filter(task => task.status === 'completed').length,
    running: tasks.filter(task => task.status === 'running').length,
    error: tasks.filter(task => task.status === 'error').length
  }
})

// 过滤后的任务列表
const filteredTasks = computed(() => {
  let tasks = [...taskStore.tasks]
  
  // 只显示Google Sheet类型的任务
  tasks = tasks.filter(task => task.task_type === 'google_sheet')
  
  // 搜索过滤
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    tasks = tasks.filter(task => 
      task.name.toLowerCase().includes(keyword) ||
      task.description.toLowerCase().includes(keyword)
    )
  }
  
  // 状态过滤
  if (statusFilter.value) {
    tasks = tasks.filter(task => task.status === statusFilter.value)
  }
  
  // 按创建时间倒序排列
  tasks.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  
  return tasks
})

// 总任务数
const totalTasks = computed(() => filteredTasks.value.length)

// 当前页任务
const currentTasks = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredTasks.value.slice(start, end)
})

// 获取表格ID
const getSheetId = (config) => {
  if (!config || !config.google_sheet_config) return '-'
  const id = config.google_sheet_config.spreadsheet_id || ''
  return id.length > 20 ? id.substring(0, 20) + '...' : id
}

// 获取工作表名称
const getSheetName = (config) => {
  if (!config || !config.google_sheet_config) return '-'
  return config.google_sheet_config.sheet_name || '-'
}

// 获取参数组合数量
const getParameterCount = (config) => {
  if (!config || !config.parameters) return 0
  try {
    let params = config.parameters
    if (typeof params === 'string') {
      params = JSON.parse(params)
    }
    
    if (Array.isArray(params)) {
      // 列表格式：返回数组长度
      return params.length
    } else if (typeof params === 'object' && params !== null) {
      // 对象格式：计算所有数组的长度乘积
      const lengths = Object.values(params).map(arr => Array.isArray(arr) ? arr.length : 0)
      return lengths.reduce((total, len) => total * (len || 1), 1)
    }
    return 0
  } catch {
    return 0
  }
}

// 刷新任务列表
const refreshTasks = async () => {
  loading.value = true
  try {
    await taskStore.fetchTasks()
    ElMessage.success('任务列表刷新成功')
  } catch (error) {
    ElMessage.error('刷新任务列表失败')
  } finally {
    loading.value = false
  }
}

// 搜索处理（防抖）
const handleSearch = debounce(() => {
  currentPage.value = 1
}, 500)

// 状态筛选处理
const handleFilter = () => {
  currentPage.value = 1
}

// 分页大小变化
const handleSizeChange = (newSize) => {
  pageSize.value = newSize
  currentPage.value = 1
}

// 当前页变化
const handleCurrentChange = (newPage) => {
  currentPage.value = newPage
}

// 切换自动刷新
const toggleAutoRefresh = (enabled) => {
  if (enabled) {
    autoRefreshTimer = setInterval(() => {
      refreshTasks()
    }, 10000) // 10秒刷新一次
  } else {
    if (autoRefreshTimer) {
      clearInterval(autoRefreshTimer)
      autoRefreshTimer = null
    }
  }
}

// 行点击处理
const handleRowClick = (row) => {
  viewTask(row.id)
}

// 查看任务详情
const viewTask = (taskId) => {
  router.push(`/google-sheet/detail?task_id=${taskId}`)
}

// 取消任务
const cancelTask = async (taskId) => {
  try {
    await taskStore.cancelTask(taskId)
    ElMessage.success('任务已取消')
  } catch (error) {
    ElMessage.error('取消任务失败')
  }
}

// 重启任务
const restartTask = async (taskId) => {
  try {
    const result = await ElMessageBox.confirm(
      '是否要重启这个任务？',
      '确认重启',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    if (result === 'confirm') {
      ElMessage.success('任务重启成功')
      await refreshTasks()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('重启任务失败')
    }
  }
}

// 复制任务
const duplicateTask = async (taskId) => {
  try {
    const task = taskStore.tasks.find(t => t.id === taskId)
    if (!task) {
      ElMessage.error('任务不存在')
      return
    }
    
    // 跳转到创建页面，并传递配置
    router.push({
      path: '/google-sheet/create',
      query: { duplicate: taskId }
    })
  } catch (error) {
    ElMessage.error('复制任务失败')
  }
}

// 导出任务配置
const exportTaskConfig = (taskId) => {
  try {
    const task = taskStore.tasks.find(t => t.id === taskId)
    if (!task) {
      ElMessage.error('任务不存在')
      return
    }
    
    const config = {
      name: task.name + '_copy',
      description: task.description,
      config: task.config
    }
    
    const configJson = JSON.stringify(config, null, 2)
    const filename = `task_config_${task.name}_${new Date().toISOString().split('T')[0]}.json`
    
    downloadFile(configJson, filename)
    ElMessage.success('配置导出成功')
  } catch (error) {
    ElMessage.error('导出配置失败')
  }
}

// 删除任务
const deleteTask = async (taskId) => {
  try {
    const result = await ElMessageBox.confirm(
      '确定要删除这个任务吗？删除后无法恢复。',
      '确认删除',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    if (result === 'confirm') {
      await taskStore.deleteTask(taskId)
      ElMessage.success('任务已删除')
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除任务失败')
    }
  }
}

// 页面加载时获取数据
onMounted(() => {
  refreshTasks()
})

// 组件卸载时清理
onBeforeUnmount(() => {
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer)
  }
})
</script>

<style scoped>
.google-sheet-index {
  padding: 0;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  gap: 16px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.stats-row {
  margin-bottom: 24px;
}

.stat-card {
  background: linear-gradient(135deg, var(--el-color-primary) 0%, var(--el-color-primary-dark-2) 100%);
  color: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
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
  font-size: 28px;
  font-weight: bold;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 14px;
  opacity: 0.9;
}

.stat-icon {
  font-size: 40px;
  opacity: 0.8;
}

.task-list-card {
  margin-bottom: 20px;
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

.task-table {
  cursor: pointer;
}

.task-table :deep(.el-table__row):hover {
  background-color: var(--el-color-primary-light-9);
}

.task-info .task-name {
  font-weight: 500;
  color: var(--el-text-color-primary);
  margin-bottom: 2px;
}

.task-info .task-description {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.progress-container {
  width: 100%;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
}

.progress-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.progress-percent {
  font-size: 12px;
  color: var(--el-text-color-regular);
  font-weight: 500;
}

.config-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.config-item {
  display: flex;
  gap: 8px;
  font-size: 12px;
}

.config-item .label {
  color: var(--el-text-color-secondary);
  min-width: 60px;
}

.config-item .value {
  color: var(--el-text-color-regular);
  font-family: monospace;
}

.text-muted {
  color: var(--el-text-color-placeholder);
}

.action-buttons {
  display: flex;
  gap: 8px;
  align-items: center;
}

.pagination-container {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

@media (max-width: 768px) {
  .toolbar {
    flex-direction: column;
    align-items: stretch;
  }
  
  .toolbar-left {
    flex-direction: column;
    align-items: stretch;
  }
  
  .toolbar-right {
    justify-content: center;
  }
  
  .stat-content {
    flex-direction: column;
    text-align: center;
    gap: 12px;
  }
  
  .stat-icon {
    font-size: 32px;
  }
  
  .stat-number {
    font-size: 24px;
  }
  
  .action-buttons {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
