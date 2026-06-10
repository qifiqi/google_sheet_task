<template>
  <div class="admin-logs">
    <PageToolbar eyebrow="管理中心" title="系统日志" description="查看系统运行日志">
      <template #actions>
        <el-switch
          v-model="autoRefresh"
          active-text="自动刷新"
          inactive-text=""
          class="mr-2"
        />
        <el-button @click="handleDownload">
          <el-icon><Download /></el-icon> 下载日志
        </el-button>
      </template>
    </PageToolbar>

    <FilterToolbar
      :filters="FILTERS"
      v-model="filterValues"
      @search="loadLogs"
      @clear="clearFilters"
      class="mb-3"
    />

    <el-card shadow="never">
      <LogViewer
        :logs="logs"
        :loading="loading"
        height="600px"
        :auto-scroll="true"
      />
    </el-card>

    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[50, 100, 200, 500]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadLogs"
        @current-change="loadLogs"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getLogs } from '@/api/config'
import PageToolbar from '@/components/PageToolbar.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import LogViewer from '@/components/LogViewer.vue'

const loading = ref(false)
const logs = ref([])
const page = ref(1)
const pageSize = ref(100)
const total = ref(0)
const autoRefresh = ref(false)
let refreshTimer = null

const filterValues = ref({ level: '', search: '', date: '' })

const FILTERS = [
  {
    key: 'level', type: 'select', label: '日志级别',
    options: [
      { label: '全部', value: '' },
      { label: 'INFO', value: 'info' },
      { label: 'WARNING', value: 'warning' },
      { label: 'ERROR', value: 'error' },
      { label: 'DEBUG', value: 'debug' },
    ],
  },
  { key: 'date', type: 'date', label: '日期' },
  { key: 'search', type: 'input', label: '搜索', placeholder: '日志内容关键词' },
]

watch(autoRefresh, (val) => {
  if (val) {
    startAutoRefresh()
  } else {
    stopAutoRefresh()
  }
})

function startAutoRefresh() {
  stopAutoRefresh()
  refreshTimer = window.setInterval(() => {
    loadLogs()
  }, 10000)
}

function stopAutoRefresh() {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
}

function clearFilters() {
  filterValues.value = { level: '', search: '', date: '' }
  page.value = 1
  loadLogs()
}

async function loadLogs() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      per_page: pageSize.value,
      ...filterValues.value,
    }
    Object.keys(params).forEach(k => { if (!params[k]) delete params[k] })
    const res = await getLogs(params)
    const data = res?.data || res || {}
    const items = data.logs || data.items || data || []
    logs.value = items.map(log => ({
      timestamp: log.timestamp || log.created_at || '',
      level: log.level || 'info',
      message: log.message || log.msg || '',
    }))
    total.value = data.total || logs.value.length
  } catch {
    logs.value = []
  } finally {
    loading.value = false
  }
}

function handleDownload() {
  const params = new URLSearchParams({
    ...filterValues.value,
    per_page: 10000,
  })
  Object.keys(filterValues.value).forEach(k => {
    if (!filterValues.value[k]) params.delete(k)
  })
  const link = document.createElement('a')
  link.href = `/api/logs/download?${params.toString()}`
  link.download = `system-logs-${new Date().toISOString().slice(0, 10)}.log`
  link.click()
  ElMessage.success('开始下载')
}

onBeforeUnmount(() => {
  stopAutoRefresh()
})

onMounted(loadLogs)
</script>

<style lang="scss" scoped>
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.mb-3 {
  margin-bottom: 12px;
}

.mr-2 {
  margin-right: 8px;
}
</style>
