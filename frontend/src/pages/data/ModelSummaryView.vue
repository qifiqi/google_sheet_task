<script setup lang="ts">
import { computed, onMounted, onUnmounted, shallowRef } from 'vue'
import { Download, Refresh, Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import ModelSummaryFilterBar from '../../components/data/ModelSummaryFilterBar.vue'
import ModelSummaryMetricGrid from '../../components/data/ModelSummaryMetricGrid.vue'
import ModelSummaryRebuildDialog from '../../components/data/ModelSummaryRebuildDialog.vue'
import ModelSummaryTable from '../../components/data/ModelSummaryTable.vue'
import { getAccessToken } from '../../api/http'
import { createDefaultModelSummaryFilters, type ModelSummaryFilters, useModelSummary } from '../../composables/useModelSummary'
import { useAuth } from '../../composables/useAuth'
import type { ModelSummaryRebuildJob, ModelSummaryStatistics } from '../../types/api'
import '../../styles/data/model-summary-page.css'

const emptySummary: ModelSummaryStatistics = { stock_count: 0, cn_stock_count: 0, us_stock_count: 0, task_count: 0, return_beats_gt_0: 0, return_beats_gt_20: 0, return_beats_gt_50: 0, return_beats_gt_100: 0 }
const auth = useAuth()
const { response, loading, errorMessage, load, startRebuild, getRebuildStatus, toQueryParams } = useModelSummary()
const activeFilters = shallowRef<ModelSummaryFilters>(createDefaultModelSummaryFilters())
const page = shallowRef(1)
const perPage = shallowRef(50)
const exportLoading = shallowRef(false)
const rebuildVisible = shallowRef(false)
const rebuildLoading = shallowRef(false)
const rebuildJob = shallowRef<ModelSummaryRebuildJob | null>(null)
let rebuildTimer: number | undefined

const summary = computed(() => response.value?.summary ?? emptySummary)
const items = computed(() => response.value?.items ?? [])
const columns = computed(() => response.value?.columns ?? [])
const pagination = computed(() => response.value?.pagination)
const summaryType = computed(() => response.value?.summary_type ?? activeFilters.value.summaryType)

function canRebuild() { return auth.hasPermission('database:model_summary') || auth.hasPermission('database:manage') }
function loadSummary(filters = activeFilters.value, targetPage = page.value, targetPerPage = perPage.value) { activeFilters.value = filters; page.value = targetPage; perPage.value = targetPerPage; return load(filters, targetPage, targetPerPage) }
function applyFilters(filters: ModelSummaryFilters) { loadSummary(filters, 1) }
function resetFilters() { loadSummary(createDefaultModelSummaryFilters(), 1) }
function refreshSummary() { loadSummary() }
function changePage(value: number) { loadSummary(activeFilters.value, value, perPage.value) }
function changePageSize(value: number) { loadSummary(activeFilters.value, 1, value) }

async function exportCsv() {
  exportLoading.value = true
  try {
    const params = toQueryParams(activeFilters.value, 1, 200)
    const response = await fetch(`/admin/api/model-summary/export?${params}`, { headers: { Authorization: `Bearer ${getAccessToken()}` } })
    if (!response.ok) throw new Error('导出失败')
    const blob = await response.blob()
    const disposition = response.headers.get('Content-Disposition') || ''
    const filename = decodeURIComponent(disposition.match(/filename\*=UTF-8''([^;]+)/)?.[1] || 'model_summary.csv')
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('CSV 已开始下载')
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '导出失败') } finally { exportLoading.value = false }
}

async function submitRebuild(options: { taskType: string; taskId: string; batchSize: number; reset: boolean }) {
  rebuildLoading.value = true
  try {
    const data = await startRebuild(options)
    rebuildJob.value = data.job
    rebuildVisible.value = false
    ElMessage.success('汇总索引已提交后台重建')
    pollRebuild(data.job.job_id)
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '重建启动失败') } finally { rebuildLoading.value = false }
}

async function pollRebuild(jobId: string) {
  window.clearTimeout(rebuildTimer)
  try {
    const data = await getRebuildStatus(jobId)
    rebuildJob.value = data.job
    if (data.job && ['pending', 'running'].includes(data.job.status)) {
      rebuildTimer = window.setTimeout(() => pollRebuild(jobId), 2000)
    } else if (data.job?.status === 'completed') {
      ElMessage.success('汇总索引重建完成')
      loadSummary()
    }
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '重建状态查询失败') }
}

onMounted(() => loadSummary())
onUnmounted(() => window.clearTimeout(rebuildTimer))
</script>

<template>
  <section class="model-summary-page">
    <header class="model-summary-page__header">
      <div class="model-summary-page__title-row">
        <h1>单模型汇总</h1>
        <span>按历史任务结果汇总最优参数与回测指标</span>
      </div>
      <div class="model-summary-page__actions">
        <el-button :icon="Refresh" @click="refreshSummary">刷新</el-button>
        <el-button type="success" :icon="Download" :loading="exportLoading" @click="exportCsv">导出 CSV</el-button>
        <el-button v-if="canRebuild()" type="primary" :icon="Setting" @click="rebuildVisible = true">重建索引</el-button>
      </div>
    </header>
    <ModelSummaryMetricGrid :summary="summary" :summary-type="summaryType" />
    <section class="model-summary-page__panel"><ModelSummaryFilterBar @apply="applyFilters" @reset="resetFilters" /><el-alert v-if="errorMessage" :title="errorMessage" type="error" :closable="false" show-icon /><div v-if="rebuildJob" class="model-summary-page__job"><span>索引重建：{{ rebuildJob.status }}</span><el-progress v-if="rebuildJob.total" :percentage="Math.round(((rebuildJob.processed || 0) / rebuildJob.total) * 100)" :stroke-width="6" /><span>{{ rebuildJob.message || rebuildJob.error || rebuildJob.job_id }}</span></div><ModelSummaryTable :items="items" :columns="columns" :loading="loading" /><footer class="model-summary-page__pagination"><span>共 {{ pagination?.total || 0 }} 条</span><el-pagination :current-page="page" :page-size="perPage" background layout="total, sizes, prev, pager, next, jumper" :page-sizes="[25, 50, 100, 200]" :total="pagination?.total || 0" @current-change="changePage" @size-change="changePageSize" /></footer></section>
    <ModelSummaryRebuildDialog v-model="rebuildVisible" :loading="rebuildLoading" :default-task-type="activeFilters.taskType" @start="submitRebuild" />
  </section>
</template>
