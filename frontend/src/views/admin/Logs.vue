<template>
  <div class="logs-page">
    <PageToolbar title="系统日志">
      <template #actions>
        <el-button :size="componentSize" @click="refreshLogs">刷新</el-button>
        <el-button :type="autoRefresh ? 'warning' : 'success'" :size="componentSize" @click="toggleAutoRefresh">
          {{ autoRefresh ? '暂停自动刷新' : '开始自动刷新' }}
        </el-button>
        <el-button type="danger" :size="componentSize" @click="handleClearLogs">清空日志</el-button>
        <el-button type="primary" :size="componentSize" @click="handleDownload">下载日志</el-button>
      </template>
    </PageToolbar>

    <FilterToolbar
      :filters="filterConfig"
      v-model="filters"
      @search="loadLogs"
      @clear="clearFilters"
    />

    <el-card shadow="never">
      <template #header>
        <div class="card-header-row">
          <span>系统日志</span>
          <el-tag size="small">{{ logs.length }}</el-tag>
        </div>
      </template>

      <div class="logs-page__viewer">
        <div v-if="loading" class="logs-page__hint">
          <el-icon class="is-loading"><Loading /></el-icon>
          加载中...
        </div>
        <template v-else-if="logs.length">
          <div
            v-for="(log, idx) in logs"
            :key="idx"
            class="logs-page__line"
            :class="`logs-page__line--${log.level || 'info'}`"
          >{{ formatLogLine(log) }}</div>
        </template>
        <div v-else class="logs-page__hint">暂无日志</div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { getLogs, getLatestLogs, getConfig } from '@/api/config'
import { useResponsive } from '@/composables/useResponsive'
import PageToolbar from '@/components/PageToolbar.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'

const { componentSize } = useResponsive()

// 日志上限（对齐静态版，避免内存占用过多）
const MAX_LOGS = 500

const logs = ref([])
const loading = ref(false)
const autoRefresh = ref(true)
const filters = ref({
  level: '',
  search: '',
  date: '',
})

// 轮询间隔读配置（log_polling_interval / log_realtime_interval，默认同静态版）
let pollIntervalMs = 5000
let realtimeIntervalMs = 3000
let pollTimer = null
let realtimeTimer = null
let lastLogTimestamp = ''

const filterConfig = [
  {
    key: 'level',
    type: 'select',
    placeholder: '全部级别',
    span: { xs: 24, sm: 6, md: 4 },
    options: [
      { value: 'info', label: '信息' },
      { value: 'warning', label: '警告' },
      { value: 'error', label: '错误' },
    ],
  },
  {
    key: 'search',
    type: 'input',
    placeholder: '搜索日志内容...',
    span: { xs: 24, sm: 6, md: 4 },
  },
  {
    key: 'date',
    type: 'date',
    placeholder: '选择日期',
    span: { xs: 24, sm: 6, md: 4 },
  },
]

async function loadLogs() {
  loading.value = true
  try {
    const params = { limit: 200 }
    if (filters.value.level) params.level = filters.value.level
    if (filters.value.search) params.search = filters.value.search
    if (filters.value.date) params.date = filters.value.date

    const res = await getLogs(params)
    logs.value = res.logs || []
    // 全量刷新后重置增量游标，避免 /logs/latest 重复追加
    lastLogTimestamp = logs.value[0]?.timestamp || ''
  } catch {
    ElMessage.error('加载日志失败')
  } finally {
    loading.value = false
  }
}

function refreshLogs() {
  loadLogs()
  ElMessage.success('日志已刷新')
}

// 实时增量：只拉取 lastLogTimestamp 之后的新日志，最新在前，超过上限截断
async function fetchLatestLogs() {
  if (!autoRefresh.value) return
  try {
    const params = { limit: 20 }
    if (lastLogTimestamp) params.since = lastLogTimestamp
    const res = await getLatestLogs(params)
    const apiLogs = res?.logs || []
    if (!apiLogs.length) return

    lastLogTimestamp = apiLogs[apiLogs.length - 1]?.timestamp || lastLogTimestamp
    const newLogs = apiLogs.slice().reverse()
    logs.value = [...newLogs, ...logs.value].slice(0, MAX_LOGS)
    ElMessage.info(`收到 ${newLogs.length} 条新日志`)
  } catch {
    // 增量轮询失败静默，等待下一轮
  }
}

function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value
}

function startTimers() {
  stopTimers()
  pollTimer = window.setInterval(() => {
    if (autoRefresh.value) loadLogs()
  }, pollIntervalMs)
  realtimeTimer = window.setInterval(fetchLatestLogs, realtimeIntervalMs)
}

function stopTimers() {
  if (pollTimer) { window.clearInterval(pollTimer); pollTimer = null }
  if (realtimeTimer) { window.clearInterval(realtimeTimer); realtimeTimer = null }
}

onMounted(async () => {
  loadLogs()
  try {
    const res = await getConfig()
    const config = res?.config || res || {}
    if (Number(config.log_polling_interval) > 0) pollIntervalMs = Number(config.log_polling_interval)
    if (Number(config.log_realtime_interval) > 0) realtimeIntervalMs = Number(config.log_realtime_interval)
  } catch {
    // 读不到配置时沿用默认间隔
  }
  startTimers()
})

onUnmounted(stopTimers)

function clearFilters() {
  filters.value = { level: '', search: '', date: '' }
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
</script>

<style scoped>
.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.logs-page__viewer {
  height: 600px;
  overflow: auto;
  padding: 12px 16px;
  border-radius: var(--el-border-radius-base);
  border: 1px solid var(--app-border);
  background: #0b1220;
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.7;
}

.logs-page__line {
  white-space: pre-wrap;
  word-break: break-all;
}

.logs-page__line--info { color: #93c5fd; }
.logs-page__line--warning { color: #fbbf24; }
.logs-page__line--error { color: #f87171; }
.logs-page__line--debug { color: #a5b4fc; }
.logs-page__line--success { color: #6ee7b7; }

.logs-page__hint {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #64748b;
  gap: 8px;
}
</style>
