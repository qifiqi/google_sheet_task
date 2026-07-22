<script setup lang="ts">
import { computed, onMounted, reactive, shallowRef } from 'vue'
import { Refresh, RefreshRight } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import XplJobTable from '../../components/tasks/XplJobTable.vue'
import { requestJson } from '../../api/http'
import { useAuth } from '../../composables/useAuth'
import type { XplJob, XplJobListResponse, XplJobStats } from '../../types/api'
import { formatDateTime, formatDuration } from '../../utils/format'
import '../../styles/tasks/xpl-operations.css'

const auth = useAuth()
const items = shallowRef<XplJob[]>([])
const stats = shallowRef<XplJobStats>({})
const loading = shallowRef(false)
const errorMessage = shallowRef('')
const filters = reactive({ taskId: '', status: '' })
const pagination = reactive({ page: 1, perPage: 20, total: 0, pages: 0 })
const operations = computed(() => [
  { label: '最早积压', value: formatDuration(stats.value._meta?.oldest_pending_seconds) },
  { label: '活跃 Worker', value: String(stats.value._meta?.running_worker_count || 0) },
  { label: '平均读取', value: formatDuration(stats.value._meta?.avg_load_elapsed_seconds) },
  { label: '平均计算', value: formatDuration(stats.value._meta?.avg_compute_elapsed_seconds) },
  { label: '平均保存', value: formatDuration(stats.value._meta?.avg_save_elapsed_seconds) },
  { label: '最近完成', value: formatDateTime(stats.value._meta?.latest_finished_at) },
])
function canRetry() { return auth.hasPermission('database:model_summary') || auth.hasPermission('database:manage') }

async function loadJobs(page = pagination.page) {
  loading.value = true; errorMessage.value = ''
  const params = new URLSearchParams({ page: String(page), per_page: String(pagination.perPage) })
  if (filters.taskId.trim()) params.set('task_id', filters.taskId.trim())
  if (filters.status) params.set('status', filters.status)
  try {
    const [jobs, statData] = await Promise.all([
      requestJson<XplJobListResponse>(`/admin/api/xpl-analysis/jobs?${params}`),
      requestJson<{ status: string; stats: XplJobStats }>(`/admin/api/xpl-analysis/jobs/stats${filters.taskId.trim() ? `?task_id=${encodeURIComponent(filters.taskId.trim())}` : ''}`),
    ])
    items.value = jobs.items; Object.assign(pagination, { page: jobs.pagination.page, total: jobs.pagination.total, pages: jobs.pagination.pages }); stats.value = statData.stats
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : '加载 XPL Job 失败' } finally { loading.value = false }
}
function search() { loadJobs(1) }
function reset() { filters.taskId = ''; filters.status = ''; loadJobs(1) }
async function retryJob(job: XplJob) { await ElMessageBox.confirm(`确定重试 Job #${job.id} 吗？`, '重试 XPL Job', { type: 'warning', confirmButtonText: '重试' }); await requestJson(`/admin/api/xpl-analysis/jobs/${job.id}/retry`, { method: 'POST' }); ElMessage.success('Job 已重置为待处理'); loadJobs() }
async function retryFailedForTask() { const taskId = filters.taskId.trim(); if (!taskId) { ElMessage.warning('请先输入任务 ID'); return }; await ElMessageBox.confirm('确定重试该任务下的所有失败 Job 吗？', '批量重试', { type: 'warning', confirmButtonText: '重试' }); const data = await requestJson<{ status: string; retried: number }>(`/admin/api/tasks/${encodeURIComponent(taskId)}/xpl-analysis/retry-failed`, { method: 'POST' }); ElMessage.success(`已重试 ${data.retried || 0} 个 Job`); loadJobs() }
onMounted(loadJobs)
</script>

<template>
  <section class="xpl-page"><header class="xpl-page__header"><div><p>任务模块</p><h1>XPL Job 运维</h1></div><span>异步计算与推送队列</span></header><div class="xpl-page__metrics"><div><span>待处理</span><strong class="is-primary">{{ stats.pending || 0 }}</strong></div><div><span>运行中</span><strong class="is-success">{{ stats.running || 0 }}</strong></div><div><span>重试中</span><strong class="is-warning">{{ stats.retrying || 0 }}</strong></div><div><span>失败</span><strong class="is-danger">{{ stats.error || 0 }}</strong></div></div><div class="xpl-page__operations" aria-label="XPL 运行指标"><div v-for="item in operations" :key="item.label"><span>{{ item.label }}</span><strong :title="item.value">{{ item.value }}</strong></div></div><section class="xpl-page__panel"><div class="xpl-page__toolbar"><el-input v-model="filters.taskId" clearable placeholder="按任务 ID 筛选" @keyup.enter="search" /><el-select v-model="filters.status" clearable placeholder="全部状态"><el-option label="待处理" value="pending" /><el-option label="运行中" value="running" /><el-option label="重试中" value="retrying" /><el-option label="已完成" value="completed" /><el-option label="失败" value="error" /><el-option label="已取消" value="cancelled" /></el-select><div class="xpl-page__toolbar-actions"><el-button type="primary" @click="search">查询</el-button><el-button @click="reset">重置</el-button><el-button v-if="canRetry()" :icon="RefreshRight" @click="retryFailedForTask">重试该任务失败项</el-button><el-button text :icon="Refresh" aria-label="刷新 XPL Job 列表" @click="() => loadJobs()" /></div></div><el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" /><XplJobTable :items="items" :loading="loading" :can-retry="canRetry()" @retry="retryJob" /><footer class="xpl-page__pagination"><span>共 {{ pagination.total }} 条</span><el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.perPage" background layout="total, sizes, prev, pager, next" :page-sizes="[20, 50, 100]" :total="pagination.total" @current-change="loadJobs" @size-change="() => loadJobs(1)" /></footer></section></section>
</template>

<style scoped>
.xpl-page { display: grid; gap: 16px; }.xpl-page__header { display: flex; align-items: end; justify-content: space-between; gap: 16px; }.xpl-page__header p { margin: 0 0 2px; color: var(--admin-text-muted); font-size: 13px; }.xpl-page__header h1 { margin: 0; color: var(--admin-text); font-size: 20px; font-weight: 600; }.xpl-page__header > span { color: var(--admin-text-muted); font-size: 13px; }.xpl-page__metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.xpl-page__metrics div { display: grid; gap: 5px; padding: 16px 20px; border-right: 1px solid var(--admin-border-light); }.xpl-page__metrics div:last-child { border-right: 0; }.xpl-page__metrics span { color: var(--admin-text-muted); font-size: 13px; }.xpl-page__metrics strong { color: var(--admin-text); font-size: 24px; font-weight: 600; }.xpl-page__metrics .is-primary { color: var(--admin-primary); }.xpl-page__metrics .is-success { color: var(--admin-success); }.xpl-page__metrics .is-warning { color: var(--admin-warning); }.xpl-page__metrics .is-danger { color: var(--admin-danger); }.xpl-page__panel { display: grid; gap: 16px; padding: 16px 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.xpl-page__toolbar { display: flex; flex-wrap: wrap; gap: 8px; }.xpl-page__toolbar :deep(.el-input), .xpl-page__toolbar :deep(.el-select) { width: 220px; }.xpl-page__toolbar-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-left: auto; }.xpl-page__pagination { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--admin-text-muted); font-size: 13px; }@media (max-width: 900px) { .xpl-page__metrics { grid-template-columns: repeat(2, 1fr); }.xpl-page__metrics div:nth-child(2) { border-right: 0; }.xpl-page__metrics div:nth-child(-n + 2) { border-bottom: 1px solid var(--admin-border-light); }.xpl-page__toolbar-actions { margin-left: 0; } }@media (max-width: 640px) { .xpl-page__header { align-items: start; flex-direction: column; gap: 4px; }.xpl-page__toolbar :deep(.el-input),.xpl-page__toolbar :deep(.el-select) { width: 100%; }.xpl-page__metrics { grid-template-columns: 1fr; }.xpl-page__metrics div { border-right: 0; border-bottom: 1px solid var(--admin-border-light); }.xpl-page__metrics div:last-child { border-bottom: 0; }.xpl-page__pagination { align-items: start; flex-direction: column; }.xpl-page__pagination :deep(.el-pagination) { flex-wrap: wrap; } }
</style>
