<template>
  <div class="logs">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="title">系统日志</h1>
      <p class="description">查看和管理系统运行日志</p>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索日志内容..."
          :prefix-icon="Search"
          clearable
          style="width: 300px"
          @input="handleSearch"
        />
        <el-select
          v-model="levelFilter"
          placeholder="日志级别"
          clearable
          style="width: 120px"
          @change="handleFilter"
        >
          <el-option label="全部" value="" />
          <el-option label="DEBUG" value="debug" />
          <el-option label="INFO" value="info" />
          <el-option label="WARNING" value="warning" />
          <el-option label="ERROR" value="error" />
        </el-select>
        <el-date-picker
          v-model="dateFilter"
          type="date"
          placeholder="选择日期"
          style="width: 150px"
          @change="handleFilter"
        />
      </div>
      <div class="toolbar-right">
        <el-button 
          :icon="Refresh" 
          @click="refreshLogs"
          :loading="loading"
        >
          刷新
        </el-button>
        <el-button 
          :icon="Download"
          @click="exportLogs"
        >
          导出日志
        </el-button>
        <el-switch
          v-model="autoRefresh"
          active-text="自动刷新"
          @change="toggleAutoRefresh"
        />
      </div>
    </div>

    <!-- 日志统计 -->
    <el-row :gutter="16" class="stats-row">
      <el-col :xs="12" :sm="6">
        <div class="stat-item">
          <div class="stat-number">{{ logStats.total }}</div>
          <div class="stat-label">总日志数</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-item error">
          <div class="stat-number">{{ logStats.error }}</div>
          <div class="stat-label">错误</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-item warning">
          <div class="stat-number">{{ logStats.warning }}</div>
          <div class="stat-label">警告</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="stat-item info">
          <div class="stat-number">{{ logStats.info }}</div>
          <div class="stat-label">信息</div>
        </div>
      </el-col>
    </el-row>

    <!-- 日志显示模式切换 -->
    <el-card class="log-card">
      <template #header>
        <div class="card-header">
          <span class="title">
            <el-icon><Document /></el-icon>
            系统日志
          </span>
          <div class="header-actions">
            <el-radio-group v-model="viewMode" size="small">
              <el-radio-button label="table">表格模式</el-radio-button>
              <el-radio-button label="console">控制台模式</el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </template>

      <!-- 表格模式 -->
      <div v-if="viewMode === 'table'" class="table-container">
        <el-table 
          :data="filteredLogs" 
          v-loading="loading"
          empty-text="暂无日志数据"
          :height="tableHeight"
        >
          <el-table-column prop="timestamp" label="时间" width="180">
            <template #default="{ row }">
              {{ formatTime(row.timestamp) }}
            </template>
          </el-table-column>
          
          <el-table-column prop="level" label="级别" width="80">
            <template #default="{ row }">
              <el-tag 
                :type="getLogLevel(row.level).type" 
                size="small"
              >
                {{ getLogLevel(row.level).text }}
              </el-tag>
            </template>
          </el-table-column>
          
          <el-table-column prop="source" label="来源" width="150" />
          
          <el-table-column prop="message" label="消息" min-width="300">
            <template #default="{ row }">
              <div class="log-message" :class="row.level">
                {{ row.message }}
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 控制台模式 -->
      <div v-else class="console-container">
        <div 
          ref="consoleRef"
          class="log-console"
          :style="{ height: tableHeight + 'px' }"
        >
          <div 
            v-for="(log, index) in filteredLogs" 
            :key="index"
            class="log-line"
            :class="log.level"
          >
            <span class="log-time">{{ formatTime(log.timestamp, 'HH:mm:ss') }}</span>
            <span class="log-level">[{{ getLogLevel(log.level).text }}]</span>
            <span class="log-source">{{ log.source }}:</span>
            <span class="log-message">{{ log.message }}</span>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 分页 -->
    <div class="pagination-container">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[50, 100, 200, 500]"
        :total="totalLogs"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../../utils/api'
import { formatTime, getLogLevel, debounce, downloadFile } from '../../utils'
import { 
  Search, 
  Refresh, 
  Download, 
  Document 
} from '@element-plus/icons-vue'

const loading = ref(false)
const autoRefresh = ref(false)
const viewMode = ref('table')
const searchKeyword = ref('')
const levelFilter = ref('')
const dateFilter = ref('')
const currentPage = ref(1)
const pageSize = ref(100)
const totalLogs = ref(0)
const tableHeight = ref(400)

const logs = ref([])
const consoleRef = ref(null)
let autoRefreshTimer = null

// 日志统计
const logStats = computed(() => {
  const stats = { total: 0, error: 0, warning: 0, info: 0, debug: 0 }
  
  logs.value.forEach(log => {
    stats.total++
    stats[log.level] = (stats[log.level] || 0) + 1
  })
  
  return stats
})

// 过滤后的日志
const filteredLogs = computed(() => {
  let filtered = [...logs.value]
  
  // 搜索过滤
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    filtered = filtered.filter(log => 
      log.message.toLowerCase().includes(keyword) ||
      log.source.toLowerCase().includes(keyword)
    )
  }
  
  // 级别过滤
  if (levelFilter.value) {
    filtered = filtered.filter(log => log.level === levelFilter.value)
  }
  
  // 日期过滤
  if (dateFilter.value) {
    const filterDate = new Date(dateFilter.value).toISOString().split('T')[0]
    filtered = filtered.filter(log => 
      log.timestamp && log.timestamp.startsWith(filterDate)
    )
  }
  
  return filtered
})

// 获取日志数据
const fetchLogs = async () => {
  loading.value = true
  try {
    const params = {
      limit: pageSize.value,
      level: levelFilter.value,
      search: searchKeyword.value,
      date: dateFilter.value ? new Date(dateFilter.value).toISOString().split('T')[0] : ''
    }
    
    const response = await api.get('/logs', { params })
    
    if (response.data.status === 'success') {
      logs.value = response.data.logs || []
      totalLogs.value = logs.value.length
      
      // 控制台模式下滚动到底部
      if (viewMode.value === 'console') {
        nextTick(() => {
          scrollToBottom()
        })
      }
    }
  } catch (error) {
    ElMessage.error('获取日志失败')
  } finally {
    loading.value = false
  }
}

// 刷新日志
const refreshLogs = () => {
  fetchLogs()
}

// 搜索处理（防抖）
const handleSearch = debounce(() => {
  currentPage.value = 1
  fetchLogs()
}, 300)

// 筛选处理
const handleFilter = () => {
  currentPage.value = 1
  fetchLogs()
}

// 分页大小变化
const handleSizeChange = (newSize) => {
  pageSize.value = newSize
  fetchLogs()
}

// 当前页变化
const handleCurrentChange = (newPage) => {
  currentPage.value = newPage
  fetchLogs()
}

// 切换自动刷新
const toggleAutoRefresh = (enabled) => {
  if (enabled) {
    autoRefreshTimer = setInterval(() => {
      fetchLogs()
    }, 5000) // 5秒刷新一次
  } else {
    if (autoRefreshTimer) {
      clearInterval(autoRefreshTimer)
      autoRefreshTimer = null
    }
  }
}

// 导出日志
const exportLogs = () => {
  const logText = filteredLogs.value.map(log => {
    return `${formatTime(log.timestamp)} [${getLogLevel(log.level).text}] ${log.source}: ${log.message}`
  }).join('\n')
  
  const filename = `logs_${new Date().toISOString().split('T')[0]}.txt`
  downloadFile(logText, filename, 'text/plain')
  
  ElMessage.success('日志导出成功')
}

// 滚动到底部
const scrollToBottom = () => {
  if (consoleRef.value) {
    consoleRef.value.scrollTop = consoleRef.value.scrollHeight
  }
}

// 计算表格高度
const calculateTableHeight = () => {
  const windowHeight = window.innerHeight
  const headerHeight = 200 // 估算的头部高度
  const footerHeight = 100 // 估算的底部高度
  tableHeight.value = Math.max(400, windowHeight - headerHeight - footerHeight)
}

// 页面加载时获取数据
onMounted(() => {
  calculateTableHeight()
  fetchLogs()
  
  // 监听窗口大小变化
  window.addEventListener('resize', calculateTableHeight)
})

// 组件卸载时清理
onBeforeUnmount(() => {
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer)
  }
  window.removeEventListener('resize', calculateTableHeight)
})
</script>

<style scoped>
.logs {
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
  margin-bottom: 20px;
}

.stat-item {
  background: var(--el-color-primary);
  color: white;
  padding: 16px;
  border-radius: 8px;
  text-align: center;
}

.stat-item.error {
  background: var(--el-color-danger);
}

.stat-item.warning {
  background: var(--el-color-warning);
}

.stat-item.info {
  background: var(--el-color-success);
}

.stat-number {
  font-size: 24px;
  font-weight: bold;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 12px;
  opacity: 0.9;
}

.log-card {
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

.log-message {
  word-break: break-all;
  line-height: 1.4;
}

.log-message.error {
  color: var(--el-color-danger);
}

.log-message.warning {
  color: var(--el-color-warning);
}

.log-message.info {
  color: var(--el-color-success);
}

.log-message.debug {
  color: var(--el-color-info);
}

.console-container {
  background: #1e1e1e;
  border-radius: 4px;
  overflow: hidden;
}

.log-console {
  background: #1e1e1e;
  color: #00ff00;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.4;
  padding: 16px;
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
  min-width: 80px;
}

.log-level {
  min-width: 60px;
  font-weight: bold;
}

.log-source {
  min-width: 120px;
  color: #ccc;
}

.log-message {
  flex: 1;
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
  
  .card-header {
    flex-direction: column;
    gap: 12px;
  }
  
  .log-line {
    flex-direction: column;
    gap: 2px;
  }
}
</style>
