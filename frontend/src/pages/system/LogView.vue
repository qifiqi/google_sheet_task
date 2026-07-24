<script setup lang="ts">
import { onMounted, onUnmounted, shallowRef, watch } from 'vue'
import { Download, Refresh, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import SystemPageHeader from '../../components/system/SystemPageHeader.vue'
import SystemLogViewer from '../../components/system/SystemLogViewer.vue'
import { useSystemLogs } from '../../composables/useSystemLogs'
import { downloadTextFile } from '../../utils/download'

const systemLogs = useSystemLogs()
const autoRefresh = shallowRef(true)
let refreshTimer: number | undefined

async function search() { await systemLogs.load() }
async function reset() { systemLogs.resetFilters(); await systemLogs.load() }
function download() {
  if (!systemLogs.logs.value.length) { ElMessage.warning('没有可下载的日志'); return }
  const content = systemLogs.logs.value.map((log) => `${log.timestamp || ''} - ${log.source || 'unknown'} - ${log.level.toUpperCase()} - ${log.message}`).join('\r\n')
  downloadTextFile(`\ufeff${content}`, `system-logs-${new Date().toISOString().slice(0, 10)}.txt`)
}
function restartTimer() {
  if (refreshTimer) window.clearInterval(refreshTimer)
  refreshTimer = undefined
  if (autoRefresh.value) refreshTimer = window.setInterval(() => systemLogs.load(), 15000)
}

watch(autoRefresh, restartTimer)
onMounted(async () => { await systemLogs.load(); restartTimer() })
onUnmounted(() => { if (refreshTimer) window.clearInterval(refreshTimer) })
</script>

<template>
  <section class="log-page">
    <SystemPageHeader section="系统模块" title="系统日志"><el-button :icon="Download" @click="download">下载当前结果</el-button><el-button :icon="autoRefresh ? VideoPause : VideoPlay" @click="autoRefresh = !autoRefresh">{{ autoRefresh ? '暂停自动刷新' : '开始自动刷新' }}</el-button><el-button type="primary" :icon="Refresh" @click="systemLogs.load">刷新</el-button></SystemPageHeader>
    <section class="log-page__panel">
      <div class="log-page__toolbar"><el-select v-model="systemLogs.filters.level" clearable placeholder="全部级别"><el-option label="错误" value="error" /><el-option label="警告" value="warning" /><el-option label="信息" value="info" /><el-option label="调试" value="debug" /></el-select><el-input v-model="systemLogs.filters.search" clearable placeholder="搜索日志内容" @keyup.enter="search" /><el-input v-model="systemLogs.filters.taskId" clearable placeholder="任务 ID" @keyup.enter="search" /><el-date-picker v-model="systemLogs.filters.date" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" /><el-select v-model="systemLogs.filters.limit"><el-option label="最近 50 条" :value="50" /><el-option label="最近 100 条" :value="100" /><el-option label="最近 200 条" :value="200" /><el-option label="最近 500 条" :value="500" /></el-select><el-button type="primary" @click="search">查询</el-button><el-button @click="reset">重置</el-button></div>
      <div class="log-page__meta"><span>共 {{ systemLogs.logs.value.length }} 条日志</span><el-tag :type="autoRefresh ? 'success' : 'info'">{{ autoRefresh ? '15 秒自动刷新' : '自动刷新已暂停' }}</el-tag></div>
      <el-alert v-if="systemLogs.errorMessage.value" :title="systemLogs.errorMessage.value" type="error" show-icon :closable="false" />
      <SystemLogViewer :logs="systemLogs.logs.value" :loading="systemLogs.loading.value" />
    </section>
  </section>
</template>

<style scoped>
.log-page { display: grid; gap: 16px; }.log-page__panel { display: grid; gap: 16px; padding: 16px 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.log-page__toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }.log-page__toolbar :deep(.el-input) { width: 220px; }.log-page__toolbar :deep(.el-select) { width: 150px; }.log-page__toolbar :deep(.el-date-editor) { width: 160px; }.log-page__meta { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--admin-text-muted); font-size: 13px; }@media (max-width: 640px) { .log-page__panel { padding: 16px; }.log-page__toolbar :deep(.el-input), .log-page__toolbar :deep(.el-select), .log-page__toolbar :deep(.el-date-editor) { width: 100%; } }
</style>
