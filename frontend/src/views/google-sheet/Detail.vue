<template>
  <div class="task-detail">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="title">任务详情</h1>
        <p class="description">{{ taskData?.name || '加载中...' }}</p>
      </div>
      <div class="header-right">
        <el-button @click="$router.go(-1)">
          返回
        </el-button>
        <el-button 
          :icon="Refresh" 
          @click="refreshTask"
          :loading="loading"
        >
          刷新
        </el-button>
      </div>
    </div>

    <div v-if="loading && !taskData" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <div v-else-if="taskData" class="task-content">
      <!-- 任务状态卡片 -->
      <el-card class="status-card">
        <div class="status-content">
          <div class="status-info">
            <div class="status-main">
              <el-tag 
                :type="getTaskStatus(taskData.status).type" 
                size="large"
                class="status-tag"
              >
                {{ getTaskStatus(taskData.status).text }}
              </el-tag>
              <span class="task-name">{{ taskData.name }}</span>
            </div>
            <div class="status-details">
              <div class="detail-item">
                <span class="label">任务ID:</span>
                <span class="value">{{ taskData.id }}</span>
              </div>
              <div class="detail-item">
                <span class="label">创建时间:</span>
                <span class="value">{{ formatTime(taskData.created_at) }}</span>
              </div>
              <div class="detail-item">
                <span class="label">更新时间:</span>
                <span class="value">{{ formatTime(taskData.updated_at) }}</span>
              </div>
            </div>
          </div>
          
          <div class="status-actions">
            <el-button 
              v-if="taskData.status === 'running'" 
              type="warning"
              @click="cancelTask"
              :loading="actionLoading"
            >
              取消任务
            </el-button>
            
            <el-button 
              v-if="['error', 'cancelled'].includes(taskData.status)" 
              type="success"
              @click="restartTask"
              :loading="actionLoading"
            >
              重启任务
            </el-button>
            
            <el-button 
              @click="duplicateTask"
            >
              复制任务
            </el-button>
            
            <el-popconfirm
              title="确定要删除这个任务吗？"
              @confirm="deleteTask"
            >
              <template #reference>
                <el-button 
                  type="danger"
                  :loading="actionLoading"
                >
                  删除任务
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </el-card>

      <!-- 进度信息 -->
      <el-card v-if="taskData.total_steps > 0" class="progress-card">
        <template #header>
          <span class="card-title">
            <el-icon><TrendCharts /></el-icon>
            执行进度
          </span>
        </template>
        
        <div class="progress-content">
          <div class="progress-info">
            <div class="progress-text">
              <span class="current">{{ taskData.current_step }}</span>
              <span class="separator">/</span>
              <span class="total">{{ taskData.total_steps }}</span>
            </div>
            <div class="progress-percent">
              {{ Math.min(100, Math.max(0, Math.round((taskData.current_step / taskData.total_steps) * 100))) }}%
            </div>
          </div>
          
          <el-progress 
            :percentage="Math.min(100, Math.max(0, Math.round((taskData.current_step / taskData.total_steps) * 100)))"
            :stroke-width="12"
            :show-text="false"
            class="progress-bar"
          />
          
          <div class="progress-stats">
            <div class="stat-item">
              <span class="label">预计剩余时间:</span>
              <span class="value">{{ estimatedTimeRemaining }}</span>
            </div>
            <div class="stat-item">
              <span class="label">平均处理时间:</span>
              <span class="value">{{ averageProcessingTime }}</span>
            </div>
          </div>
        </div>
      </el-card>

      <!-- 配置信息 -->
      <el-card class="config-card">
        <template #header>
          <span class="card-title">
            <el-icon><Setting /></el-icon>
            配置信息
          </span>
        </template>
        
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务类型">
            <el-tag>{{ taskData.task_type }}</el-tag>
          </el-descriptions-item>
          
          <el-descriptions-item label="任务描述">
            {{ taskData.description || '无描述' }}
          </el-descriptions-item>
          
          <el-descriptions-item label="电子表格ID">
            <code class="config-value">{{ getConfigValue('google_sheet_config.spreadsheet_id') }}</code>
          </el-descriptions-item>
          
          <el-descriptions-item label="工作表名称">
            <code class="config-value">{{ getConfigValue('google_sheet_config.sheet_name') }}</code>
          </el-descriptions-item>
          
          <el-descriptions-item label="Token文件">
            <code class="config-value">{{ getConfigValue('google_sheet_config.token_file') }}</code>
          </el-descriptions-item>
          
          <el-descriptions-item label="请求间隔">
            {{ getConfigValue('google_sheet_config.request_interval') }}ms
          </el-descriptions-item>
          
          <el-descriptions-item label="重试次数">
            {{ getConfigValue('google_sheet_config.retry_count') }}
          </el-descriptions-item>
          
          <el-descriptions-item label="参数组合数">
            {{ getParameterCombinationCount() }}
          </el-descriptions-item>
        </el-descriptions>
        
        <!-- 位置配置 -->
        <div class="position-config">
          <h4>位置配置</h4>
          <el-tabs>
            <el-tab-pane label="参数位置">
              <div class="position-list">
                <div 
                  v-for="(position, name) in getConfigValue('google_sheet_config.parameter_positions')" 
                  :key="name"
                  class="position-item"
                >
                  <span class="position-name">{{ name }}:</span>
                  <code class="position-value">{{ position }}</code>
                </div>
              </div>
            </el-tab-pane>
            
            <el-tab-pane label="检查位置">
              <div class="position-list">
                <div 
                  v-for="(position, name) in getConfigValue('google_sheet_config.check_positions')" 
                  :key="name"
                  class="position-item"
                >
                  <span class="position-name">{{ name }}:</span>
                  <code class="position-value">{{ position }}</code>
                </div>
              </div>
            </el-tab-pane>
            
            <el-tab-pane label="结果位置">
              <div class="position-list">
                <div 
                  v-for="(position, name) in getConfigValue('google_sheet_config.result_positions')" 
                  :key="name"
                  class="position-item"
                >
                  <span class="position-name">{{ name }}:</span>
                  <code class="position-value">{{ position }}</code>
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>
      </el-card>

      <!-- 日志和结果 -->
      <el-row :gutter="20">
        <el-col :xs="24" :lg="12">
          <!-- 任务日志 -->
          <el-card class="log-card">
            <template #header>
              <div class="card-header">
                <span class="card-title">
                  <el-icon><Document /></el-icon>
                  任务日志
                </span>
                <div class="header-actions">
                  <el-switch
                    v-model="autoRefreshLogs"
                    active-text="自动刷新"
                    size="small"
                    @change="toggleAutoRefreshLogs"
                  />
                  <el-button 
                    size="small"
                    @click="refreshLogs"
                    :loading="logsLoading"
                  >
                    刷新
                  </el-button>
                </div>
              </div>
            </template>
            
            <div class="log-container" ref="logContainerRef">
              <div 
                v-for="(log, index) in taskLogs" 
                :key="index"
                class="log-line"
                :class="log.level"
              >
                <span class="log-time">{{ formatTime(log.timestamp, 'HH:mm:ss') }}</span>
                <span class="log-level">[{{ getLogLevel(log.level).text }}]</span>
                <span class="log-message">{{ log.message }}</span>
              </div>
              
              <div v-if="taskLogs.length === 0" class="empty-logs">
                暂无日志数据
              </div>
            </div>
          </el-card>
        </el-col>
        
        <el-col :xs="24" :lg="12">
          <!-- 任务结果 -->
          <el-card class="result-card">
            <template #header>
              <div class="card-header">
                <span class="card-title">
                  <el-icon><DataAnalysis /></el-icon>
                  执行结果
                </span>
                <div class="header-actions">
                  <el-button 
                    size="small"
                    @click="exportResults"
                    :disabled="taskResults.length === 0"
                  >
                    导出结果
                  </el-button>
                  <el-button 
                    size="small"
                    @click="refreshResults"
                    :loading="resultsLoading"
                  >
                    刷新
                  </el-button>
                </div>
              </div>
            </template>
            
            <div class="result-container">
              <div v-if="taskResults.length > 0" class="result-list">
                <div 
                  v-for="(result, index) in taskResults" 
                  :key="index"
                  class="result-item"
                >
                  <div class="result-header">
                    <span class="result-index">#{{ index + 1 }}</span>
                    <span class="result-time">{{ formatTime(result.timestamp) }}</span>
                  </div>
                  <div class="result-content">
                    <pre class="result-data">{{ formatResultData(result.data) }}</pre>
                  </div>
                </div>
              </div>
              
              <div v-else class="empty-results">
                <el-empty description="暂无结果数据" />
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 实时事件监听 -->
      <div v-if="taskData.status === 'running'" class="event-listener">
        <!-- 这里可以显示实时事件，如确认请求等 -->
      </div>
    </div>

    <div v-else class="error-container">
      <el-result
        icon="error"
        title="任务不存在"
        sub-title="请检查任务ID是否正确"
      >
        <template #extra>
          <el-button type="primary" @click="$router.push('/google-sheet/index')">
            返回任务列表
          </el-button>
        </template>
      </el-result>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTaskStore } from '../../stores'
import { formatTime, getTaskStatus, getLogLevel, downloadFile } from '../../utils'
import { 
  Refresh, 
  TrendCharts, 
  Setting, 
  Document, 
  DataAnalysis 
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const taskStore = useTaskStore()

const loading = ref(false)
const actionLoading = ref(false)
const logsLoading = ref(false)
const resultsLoading = ref(false)
const autoRefreshLogs = ref(false)

const taskData = ref(null)
const taskLogs = ref([])
const taskResults = ref([])

const logContainerRef = ref(null)

let refreshTimer = null
let logsRefreshTimer = null

// 任务ID
const taskId = computed(() => route.query.task_id)

// 预计剩余时间
const estimatedTimeRemaining = computed(() => {
  if (!taskData.value || taskData.value.status !== 'running') return '-'
  
  const { current_step, total_steps, created_at } = taskData.value
  if (current_step === 0) return '计算中...'
  
  const elapsed = Date.now() - new Date(created_at).getTime()
  const avgTime = elapsed / current_step
  const remaining = (total_steps - current_step) * avgTime
  
  return formatDuration(remaining)
})

// 平均处理时间
const averageProcessingTime = computed(() => {
  if (!taskData.value || taskData.value.current_step === 0) return '-'
  
  const { current_step, created_at } = taskData.value
  const elapsed = Date.now() - new Date(created_at).getTime()
  const avgTime = elapsed / current_step
  
  return formatDuration(avgTime)
})

// 获取配置值
const getConfigValue = (path) => {
  if (!taskData.value) return '-'
  
  const keys = path.split('.')
  let value = taskData.value
  
  // 如果路径以 google_sheet_config 开头，直接从 taskData.value 中获取
  if (path.startsWith('google_sheet_config')) {
    value = taskData.value.google_sheet_config || {}
    keys.shift() // 移除 google_sheet_config
  } else if (path.startsWith('config.')) {
    value = taskData.value.config || {}
    keys.shift() // 移除 config
  }
  
  for (const key of keys) {
    if (value && typeof value === 'object' && key in value) {
      value = value[key]
    } else {
      return '-'
    }
  }
  
  if (value === null || value === undefined) return '-'
  return value
}

// 获取参数组合数量
const getParameterCombinationCount = () => {
  const parameters = getConfigValue('parameters')
  if (parameters === '-') return 0
  
  try {
    let params = parameters
    if (typeof params === 'string') {
      params = JSON.parse(params)
    }
    
    if (Array.isArray(params)) {
      // 列表格式：计算每个数组长度的乘积
      return params.reduce((total, group) => total * (Array.isArray(group) ? group.length || 1 : 1), 1)
    } else if (typeof params === 'object' && params !== null) {
      // 对象格式：计算所有数组的长度乘积
      const lengths = Object.values(params).map(arr => Array.isArray(arr) ? arr.length : 1)
      return lengths.reduce((total, len) => total * len, 1)
    }
    return 0
  } catch (error) {
    console.error('计算参数组合数失败:', error)
    return 0
  }
}

// 格式化持续时间
const formatDuration = (ms) => {
  if (ms < 1000) return '< 1秒'
  
  const seconds = Math.floor(ms / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  
  if (hours > 0) {
    return `${hours}小时${minutes % 60}分钟`
  } else if (minutes > 0) {
    return `${minutes}分钟${seconds % 60}秒`
  } else {
    return `${seconds}秒`
  }
}

// 格式化结果数据
const formatResultData = (data) => {
  if (typeof data === 'object') {
    return JSON.stringify(data, null, 2)
  }
  return String(data)
}

// 刷新任务数据
const refreshTask = async () => {
  if (!taskId.value) return
  
  loading.value = true
  try {
    await taskStore.fetchTask(taskId.value)
    taskData.value = taskStore.currentTask
  } catch (error) {
    ElMessage.error('刷新任务数据失败')
  } finally {
    loading.value = false
  }
}

// 刷新日志
const refreshLogs = async () => {
  if (!taskId.value) return
  
  logsLoading.value = true
  try {
    await taskStore.fetchTaskLogs(taskId.value)
    taskLogs.value = taskStore.taskLogs
    
    // 滚动到底部
    nextTick(() => {
      scrollLogsToBottom()
    })
  } catch (error) {
    ElMessage.error('刷新日志失败')
  } finally {
    logsLoading.value = false
  }
}

// 刷新结果
const refreshResults = async () => {
  if (!taskId.value) return
  
  resultsLoading.value = true
  try {
    await taskStore.fetchTaskResults(taskId.value)
    taskResults.value = taskStore.taskResults
  } catch (error) {
    ElMessage.error('刷新结果失败')
  } finally {
    resultsLoading.value = false
  }
}

// 切换日志自动刷新
const toggleAutoRefreshLogs = (enabled) => {
  if (enabled) {
    logsRefreshTimer = setInterval(() => {
      refreshLogs()
    }, 3000) // 3秒刷新一次
  } else {
    if (logsRefreshTimer) {
      clearInterval(logsRefreshTimer)
      logsRefreshTimer = null
    }
  }
}

// 滚动日志到底部
const scrollLogsToBottom = () => {
  if (logContainerRef.value) {
    logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
  }
}

// 取消任务
const cancelTask = async () => {
  try {
    const result = await ElMessageBox.confirm(
      '确定要取消这个任务吗？',
      '确认取消',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    if (result === 'confirm') {
      actionLoading.value = true
      await taskStore.cancelTask(taskId.value)
      ElMessage.success('任务已取消')
      await refreshTask()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('取消任务失败')
    }
  } finally {
    actionLoading.value = false
  }
}

// 重启任务
const restartTask = async () => {
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
      actionLoading.value = true
      // 这里应该调用重启任务的API
      ElMessage.success('任务重启成功')
      await refreshTask()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('重启任务失败')
    }
  } finally {
    actionLoading.value = false
  }
}

// 复制任务
const duplicateTask = () => {
  router.push({
    path: '/google-sheet/create',
    query: { duplicate: taskId.value }
  })
}

// 删除任务
const deleteTask = async () => {
  try {
    actionLoading.value = true
    await taskStore.deleteTask(taskId.value)
    ElMessage.success('任务已删除')
    router.push('/google-sheet/index')
  } catch (error) {
    ElMessage.error('删除任务失败')
  } finally {
    actionLoading.value = false
  }
}

// 导出结果
const exportResults = () => {
  if (taskResults.value.length === 0) {
    ElMessage.warning('暂无结果数据')
    return
  }
  
  const data = taskResults.value.map((result, index) => ({
    序号: index + 1,
    时间: formatTime(result.timestamp),
    结果: result.data
  }))
  
  const csvContent = convertToCSV(data)
  const filename = `task_results_${taskData.value.name}_${new Date().toISOString().split('T')[0]}.csv`
  
  downloadFile(csvContent, filename, 'text/csv')
  ElMessage.success('结果导出成功')
}

// 转换为CSV格式
const convertToCSV = (data) => {
  if (data.length === 0) return ''
  
  const headers = Object.keys(data[0])
  const csvRows = [
    headers.join(','),
    ...data.map(row => 
      headers.map(header => {
        const value = row[header]
        return typeof value === 'object' ? JSON.stringify(value) : String(value)
      }).join(',')
    )
  ]
  
  return csvRows.join('\n')
}

// 页面加载时获取数据
onMounted(async () => {
  if (!taskId.value) {
    ElMessage.error('任务ID不能为空')
    router.push('/google-sheet/index')
    return
  }
  
  // 获取任务详情
  await refreshTask()
  
  // 获取日志和结果
  await Promise.all([
    refreshLogs(),
    refreshResults()
  ])
  
  // 如果任务正在运行，启动自动刷新
  if (taskData.value?.status === 'running') {
    // 使用递归的 setTimeout 代替 setInterval，避免任务堆积
    const scheduleNextRefresh = async () => {
      if (!taskData.value || taskData.value.status !== 'running') return
      
      try {
        await refreshTask()
        refreshTimer = setTimeout(scheduleNextRefresh, 5000)
      } catch (error) {
        console.error('自动刷新失败:', error)
        // 如果刷新失败，延长下次刷新间隔
        refreshTimer = setTimeout(scheduleNextRefresh, 10000)
      }
    }
    
    scheduleNextRefresh()
    
    // 日志自动刷新
    autoRefreshLogs.value = true
    toggleAutoRefreshLogs(true)
  }
})

// 组件卸载时清理定时器
onBeforeUnmount(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
  if (logsRefreshTimer) {
    clearInterval(logsRefreshTimer)
  }
})
</script>

<style scoped>
.task-detail {
  padding: 0;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.header-left .title {
  margin-bottom: 4px;
}

.header-left .description {
  color: var(--el-text-color-secondary);
  margin: 0;
}

.header-right {
  display: flex;
  gap: 12px;
}

.loading-container {
  padding: 40px;
}

.task-content > .el-card {
  margin-bottom: 20px;
}

.status-card {
  border-left: 4px solid var(--el-color-primary);
}

.status-content {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.status-main {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.status-tag {
  font-size: 14px;
  padding: 8px 16px;
}

.task-name {
  font-size: 18px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.status-details {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-item {
  display: flex;
  gap: 8px;
  font-size: 14px;
}

.detail-item .label {
  color: var(--el-text-color-secondary);
  min-width: 80px;
}

.detail-item .value {
  color: var(--el-text-color-regular);
  font-family: monospace;
}

.status-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.progress-content {
  padding: 16px 0;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.progress-text {
  font-size: 18px;
  font-weight: 500;
}

.progress-text .current {
  color: var(--el-color-primary);
}

.progress-text .separator {
  color: var(--el-text-color-secondary);
  margin: 0 8px;
}

.progress-text .total {
  color: var(--el-text-color-regular);
}

.progress-percent {
  font-size: 24px;
  font-weight: bold;
  color: var(--el-color-primary);
}

.progress-bar {
  margin-bottom: 16px;
}

.progress-stats {
  display: flex;
  justify-content: space-between;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-item .label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.stat-item .value {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.config-value {
  background: var(--el-color-info-light-9);
  padding: 2px 6px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 12px;
}

.position-config {
  margin-top: 24px;
}

.position-config h4 {
  margin-bottom: 16px;
  color: var(--el-text-color-primary);
}

.position-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.position-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.position-name {
  min-width: 100px;
  color: var(--el-text-color-regular);
}

.position-value {
  background: var(--el-color-info-light-9);
  padding: 2px 6px;
  border-radius: 3px;
  font-family: monospace;
  font-size: 12px;
}

.log-container {
  background: #1e1e1e;
  color: #00ff00;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.4;
  padding: 16px;
  border-radius: 4px;
  height: 400px;
  overflow-y: auto;
}

.log-line {
  margin-bottom: 2px;
  display: flex;
  gap: 8px;
}

.log-line.error {
  color: #ff6b6b;
}

.log-line.warning {
  color: #ffd93d;
}

.log-line.info {
  color: #6bcf7f;
}

.log-line.debug {
  color: #74c0fc;
}

.log-time {
  color: #888;
  min-width: 60px;
}

.log-level {
  min-width: 50px;
  font-weight: bold;
}

.log-message {
  flex: 1;
}

.empty-logs {
  text-align: center;
  color: #888;
  padding: 40px 0;
}

.result-container {
  max-height: 400px;
  overflow-y: auto;
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.result-item {
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  overflow: hidden;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--el-color-info-light-9);
  border-bottom: 1px solid var(--el-border-color-light);
}

.result-index {
  font-weight: 500;
  color: var(--el-color-primary);
}

.result-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.result-content {
  padding: 12px;
}

.result-data {
  margin: 0;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.4;
  background: var(--el-color-info-light-9);
  padding: 8px;
  border-radius: 3px;
  overflow-x: auto;
}

.empty-results {
  padding: 40px 0;
}

.error-container {
  padding: 40px 0;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: 16px;
  }
  
  .status-content {
    flex-direction: column;
    gap: 20px;
  }
  
  .status-actions {
    justify-content: center;
  }
  
  .progress-stats {
    flex-direction: column;
    gap: 12px;
  }
  
  .card-header {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
  }
  
  .position-item {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
