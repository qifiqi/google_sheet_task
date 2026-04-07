<template>
  <div class="logs-page">
    <div class="page-toolbar">
      <h2 style="margin: 0">系统日志</h2>
      <div class="page-toolbar__actions">
        <el-button :size="componentSize" @click="loadLogs">刷新</el-button>
        <el-button type="danger" :size="componentSize" @click="handleClearLogs">清空日志</el-button>
        <el-button type="primary" :size="componentSize" @click="handleDownload">下载日志</el-button>
      </div>
    </div>

    <el-card shadow="never" style="margin-bottom: 16px">
      <el-row :gutter="12" align="bottom">
        <el-col :xs="24" :sm="6">
          <div class="filter-label">日志级别</div>
          <el-select v-model="filters.level" placeholder="全部级别" clearable style="width: 100%" @change="loadLogs">
            <el-option value="info" label="信息" />
            <el-option value="warning" label="警告" />
            <el-option value="error" label="错误" />
          </el-select>
        </el-col>
        <el-col :xs="24" :sm="6">
          <div class="filter-label">搜索</div>
          <el-input v-model="filters.search" placeholder="搜索日志内容..." clearable @keyup.enter="loadLogs" />
        </el-col>
        <el-col :xs="24" :sm="6">
          <div class="filter-label">日期筛选</div>
          <el-date-picker
            v-model="filters.date"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 100%"
            @change="loadLogs"
          />
        </el-col>
        <el-col :xs="24" :sm="6">
          <el-button :size="componentSize" class="logs-clear-btn" @click="clearFilters">清除筛选</el-button>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-header-row">
          <span>系统日志</span>
          <el-tag size="small">{{ logs.length }}</el-tag>
        </div>
      </template>

      <div ref="logContainerRef" v-loading="loading" class="log-container">
        <div v-if="!logs.length" class="empty-log">暂无日志</div>
        <div v-for="(log, index) in logs" :key="index" :class="['log-line', `log-${log.level}`]">
          {{ formatLogLine(log) }}
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getLogs } from '@/api/config'
import { useResponsive } from '@/composables/useResponsive'

const { componentSize } = useResponsive()

const logs = ref([])
const loading = ref(false)
const logContainerRef = ref()
const filters = reactive({
  level: '',
  search: '',
  date: '',
})
let refreshTimer = null

async function loadLogs() {
  loading.value = true
  try {
    const params = { limit: 200 }
    if (filters.level) params.level = filters.level
    if (filters.search) params.search = filters.search
    if (filters.date) params.date = filters.date

    const res = await getLogs(params)
    logs.value = res.logs || []

    setTimeout(() => {
      if (logContainerRef.value) {
        logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
      }
    }, 50)
  } catch {
    ElMessage.error('加载日志失败')
  } finally {
    loading.value = false
  }
}

function clearFilters() {
  filters.level = ''
  filters.search = ''
  filters.date = ''
  loadLogs()
}

function formatLogLine(log) {
  const time = log.timestamp ? new Date(log.timestamp).toLocaleString('zh-CN') : '-'
  const level = (log.level || 'info').toUpperCase()
  const source = log.source ? `[${log.source}] ` : ''
  return `[${time}] [${level}] ${source}${log.message || ''}`
}

function handleClearLogs() {
  ElMessage.warning('清空日志功能暂未实现')
}

function handleDownload() {
  if (!logs.value.length) {
    ElMessage.warning('没有日志可下载')
    return
  }

  const text = logs.value.map((log) => formatLogLine(log)).join('\n')
  const blob = new Blob([text], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `system_logs_${new Date().toISOString().split('T')[0]}.txt`
  link.click()
  URL.revokeObjectURL(url)
  ElMessage.success('日志下载完成')
}

onMounted(() => {
  loadLogs()
  refreshTimer = setInterval(loadLogs, 5000)
})

onUnmounted(() => {
  clearInterval(refreshTimer)
})
</script>

<style scoped>
.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.filter-label {
  margin-bottom: 4px;
  font-size: 13px;
}

.logs-clear-btn {
  margin-top: 20px;
}

.log-container {
  height: 600px;
  overflow-y: auto;
  background: #0b1220;
  color: #dbeafe;
  padding: 12px 14px;
  border-radius: 6px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
}

.empty-log {
  text-align: center;
  color: #909399;
  padding: 20px;
}

.log-line {
  white-space: pre;
  word-break: normal;
}

.log-info {
  color: #93c5fd;
}

.log-warning {
  color: #fcd34d;
}

.log-error {
  color: #fca5a5;
}

@media (max-width: 768px) {
  .logs-clear-btn {
    margin-top: 0;
    width: 100%;
  }

  .log-container {
    height: calc(100vh - 320px);
    min-height: 360px;
  }
}
</style>
