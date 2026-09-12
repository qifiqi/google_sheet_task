<template>
  <div class="logs-page">
    <PageToolbar title="系统日志">
      <template #actions>
        <el-button :size="componentSize" @click="loadLogs">刷新</el-button>
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

      <LogViewer :logs="logs" height="600px" :loading="loading" />
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getLogs } from '@/api/config'
import { useResponsive } from '@/composables/useResponsive'
import { usePolling } from '@/composables/usePolling'
import PageToolbar from '@/components/PageToolbar.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import LogViewer from '@/components/LogViewer.vue'

const { componentSize } = useResponsive()

const logs = ref([])
const loading = ref(false)
const filters = ref({
  level: '',
  search: '',
  date: '',
})

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
  } catch {
    ElMessage.error('加载日志失败')
  } finally {
    loading.value = false
  }
}

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

usePolling(loadLogs, { interval: 5000, immediate: true })
</script>

<style scoped>
.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
