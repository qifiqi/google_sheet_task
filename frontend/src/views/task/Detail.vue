<template>
  <div class="app-page task-detail-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Task Monitor</div>
        <h2 class="page-title">任务详情</h2>
        <p class="page-description">查看任务状态、执行日志、结果趋势和当前配置，支持停止与重启任务。</p>
      </div>
      <div class="page-toolbar__actions">
        <el-button @click="checkStatus">检查状态</el-button>
        <el-button v-if="task?.status === 'running'" type="warning" @click="handleCancel">停止任务</el-button>
        <el-dropdown v-if="task && task.status !== 'running'" @command="handleRestart">
          <el-button type="success">
            重启任务
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="resume">从断点重启</el-dropdown-item>
              <el-dropdown-item command="fresh">从头重启</el-dropdown-item>
              <el-dropdown-item command="create" divided>跳转到创建重启任务</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button class="page-back-button" @click="$router.back()">返回</el-button>
      </div>
    </div>

    <div v-loading="loading">
      <el-row v-if="task" :gutter="16" class="task-detail-page__metrics">
        <el-col :xs="24" :md="8" class="task-detail-page__metric-col">
          <el-card shadow="never" class="page-section task-detail-page__metric-card">
            <div class="section-heading">
              <h3 class="section-title section-title--muted">任务信息</h3>
            </div>
            <el-descriptions :column="1" size="small">
              <el-descriptions-item label="任务名称">{{ task.name }}</el-descriptions-item>
              <el-descriptions-item label="任务 ID">
                <span class="inline-muted font-mono">{{ task.id }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="状态">
                <StatusTag :status="task.status" />
              </el-descriptions-item>
              <el-descriptions-item label="进度">
                <el-progress
                  v-if="task.total_steps > 0"
                  :percentage="taskProgressPercent"
                  :format="() => `${task.current_step || 0}/${task.total_steps}`"
                />
                <span v-else>-</span>
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>

        <el-col :xs="24" :md="8" class="task-detail-page__metric-col">
          <el-card shadow="never" class="page-section task-detail-page__metric-card">
            <div class="section-heading">
              <h3 class="section-title section-title--muted">时间信息</h3>
            </div>
            <el-descriptions :column="1" size="small">
              <el-descriptions-item label="开始时间">{{ task.start_time || '-' }}</el-descriptions-item>
              <el-descriptions-item label="结束时间">{{ task.end_time || '-' }}</el-descriptions-item>
              <el-descriptions-item label="执行时长">
                {{ task.duration_seconds != null ? `${task.duration_seconds}s` : '-' }}
              </el-descriptions-item>
              <el-descriptions-item v-if="task.error_message" label="错误信息">
                <span class="task-detail-page__error-text">{{ task.error_message }}</span>
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>

        <el-col :xs="24" :md="8" class="task-detail-page__metric-col">
          <div class="hero-panel task-detail-page__hero">
            <div class="hero-panel__eyebrow">Execution Summary</div>
            <div class="task-detail-page__hero-stats">
              <div class="task-detail-page__hero-stat">
                <div class="task-detail-page__hero-value">{{ resultSummary.success_count ?? 0 }}</div>
                <div class="task-detail-page__hero-label">成功</div>
              </div>
              <div class="task-detail-page__hero-stat">
                <div class="task-detail-page__hero-value">{{ resultSummary.failed_count ?? 0 }}</div>
                <div class="task-detail-page__hero-label">失败</div>
              </div>
            </div>
            <el-progress
              :percentage="resultSummary.success_rate ?? 0"
              :show-text="false"
              color="#ffffff"
              class="task-detail-page__hero-progress"
            />
            <div class="task-detail-page__hero-foot">
              成功率 {{ resultSummary.success_rate ?? 0 }}%
            </div>
          </div>
        </el-col>
      </el-row>

      <el-card v-if="task" shadow="never" class="page-section">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="任务日志" name="logs">
            <div class="task-detail-page__log-panel">
              <div v-if="!logs.length" class="panel-note panel-note--center task-detail-page__log-empty">暂无日志</div>
              <div v-for="(log, i) in logs" :key="i" :class="['log-line', `log-${log.level}`]">
                [{{ log.timestamp }}] [{{ (log.level || 'info').toUpperCase() }}] {{ log.message }}
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="执行结果" name="results">
            <div class="section-heading task-detail-page__results-head">
              <div class="control-row">
                <el-radio-group v-model="resultFilter" size="small">
                  <el-radio-button value="all">全部</el-radio-button>
                  <el-radio-button value="success">成功</el-radio-button>
                  <el-radio-button value="failed">失败</el-radio-button>
                </el-radio-group>
                <span class="panel-note">共 {{ filteredResultTotal }} 条</span>
              </div>
              <div class="section-actions">
                <el-button size="small" @click="loadResults">刷新结果</el-button>
              </div>
            </div>

            <div class="sub-card task-detail-page__chart-card">
              <div class="task-detail-page__chart-title">结果趋势</div>
              <div class="task-detail-page__chart-wrap">
                <canvas ref="resultChartRef"></canvas>
              </div>
            </div>

            <el-table :data="paginatedResults" stripe class="task-detail-page__table">
              <el-table-column prop="step_index" label="步骤" width="70" />
              <el-table-column label="状态" width="80">
                <template #default="{ row }">
                  <el-tag :type="row.success ? 'success' : 'danger'" size="small">
                    {{ row.success ? '成功' : '失败' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="参数" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">{{ JSON.stringify(row.parameters) }}</template>
              </el-table-column>
              <el-table-column label="执行结果" min-width="220" show-overflow-tooltip>
                <template #default="{ row }">{{ formatResultPreview(row.result) }}</template>
              </el-table-column>
              <el-table-column prop="timestamp" label="时间" width="160" show-overflow-tooltip />
              <el-table-column label="耗时" width="90">
                <template #default="{ row }">{{ formatDurationValue(row.execution_time) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-button link type="primary" @click="viewResult(row)">查看</el-button>
                </template>
              </el-table-column>
            </el-table>

            <div class="task-detail-page__pagination">
              <el-pagination
                v-model:current-page="resultPage"
                v-model:page-size="resultPageSize"
                :total="filteredResultTotal"
                :page-sizes="[20, 50, 100]"
                layout="total, sizes, prev, pager, next"
                @current-change="scrollResultsToTop"
                @size-change="handleResultPageSizeChange"
              />
            </div>
          </el-tab-pane>

          <el-tab-pane label="任务配置" name="config">
            <el-row :gutter="16" class="task-detail-page__config-grid">
              <el-col :xs="24" :md="12" class="task-detail-page__config-col">
                <div class="sub-card task-detail-page__config-card">
                  <div class="task-detail-page__chart-title">Google Sheet 配置</div>
                  <el-descriptions :column="1" border>
                    <el-descriptions-item label="Spreadsheet ID">
                      {{ taskConfigSummary.spreadsheetId }}
                    </el-descriptions-item>
                    <el-descriptions-item label="Sheet 名称">
                      {{ taskConfigSummary.sheetName }}
                    </el-descriptions-item>
                    <el-descriptions-item label="表标题">
                      {{ taskConfigSummary.title }}
                    </el-descriptions-item>
                    <el-descriptions-item label="Token">
                      {{ taskConfigSummary.token }}
                    </el-descriptions-item>
                    <el-descriptions-item label="代理">
                      {{ taskConfigSummary.proxy }}
                    </el-descriptions-item>
                  </el-descriptions>
                </div>
              </el-col>
              <el-col :xs="24" :md="12" class="task-detail-page__config-col">
                <div class="sub-card task-detail-page__config-card">
                  <div class="task-detail-page__chart-title">参数配置</div>
                  <el-descriptions :column="1" border>
                    <el-descriptions-item label="参数组数">
                      {{ taskConfigSummary.parameterGroups }}
                    </el-descriptions-item>
                    <el-descriptions-item label="位置配置">
                      {{ taskConfigSummary.positionSummary }}
                    </el-descriptions-item>
                    <el-descriptions-item label="扩展设置">
                      {{ taskConfigSummary.extraSummary }}
                    </el-descriptions-item>
                  </el-descriptions>
                </div>
              </el-col>
            </el-row>

            <div class="sub-card">
              <div class="task-detail-page__chart-title">完整配置</div>
              <pre class="code-block task-detail-page__config-code">{{ JSON.stringify(task.config || {}, null, 2) }}</pre>
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </div>

    <el-drawer v-model="resultDrawerVisible" title="结果详情" :size="isMobile ? '100%' : '560px'">
      <div v-if="currentResult" class="task-detail-page__drawer-body">
        <div class="task-detail-page__drawer-section">
          <div class="task-detail-page__chart-title">参数信息</div>
          <pre class="code-block task-detail-page__drawer-code">{{ JSON.stringify(currentResult.parameters, null, 2) }}</pre>
        </div>
        <div class="task-detail-page__drawer-section">
          <div class="task-detail-page__chart-title">执行结果</div>
          <pre class="code-block task-detail-page__drawer-code">{{ JSON.stringify(currentResult.result, null, 2) }}</pre>
        </div>
        <div v-if="currentResult.error_message" class="task-detail-page__drawer-section">
          <div class="task-detail-page__chart-title">错误信息</div>
          <pre class="task-detail-page__error-block">{{ currentResult.error_message }}</pre>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import {
  getTask,
  getTaskLogs,
  getTaskResults,
  cancelTask,
  restartTask,
  checkTaskStatus as apiCheckStatus
} from '@/api/task'
import StatusTag from '@/components/StatusTag.vue'
import { useChartJs } from '@/composables/useChartJs'
import { usePolling } from '@/composables/usePolling'
import { useResponsive } from '@/composables/useResponsive'

const route = useRoute()
const router = useRouter()
const { isMobile } = useResponsive()
const taskId = route.params.id
const task = ref(null)
const logs = ref([])
const allResults = ref([])
const resultSummary = ref({})
const loading = ref(false)
const activeTab = ref('logs')
const logContainerRef = ref()
const resultPage = ref(1)
const resultPageSize = ref(20)
const resultFilter = ref('all')
const resultDrawerVisible = ref(false)
const currentResult = ref(null)
const resultChartRef = ref(null)
let resultChart = null
const { loadChartJs } = useChartJs()

const taskProgressPercent = computed(() => {
  if (!task.value?.total_steps) return 0
  return Math.min(100, Math.round(((task.value.current_step || 0) / task.value.total_steps) * 100))
})

const filteredResults = computed(() => {
  if (resultFilter.value === 'success') return allResults.value.filter((item) => item.success)
  if (resultFilter.value === 'failed') return allResults.value.filter((item) => !item.success)
  return allResults.value
})

const filteredResultTotal = computed(() => filteredResults.value.length)

const paginatedResults = computed(() => {
  const start = (resultPage.value - 1) * resultPageSize.value
  return filteredResults.value.slice(start, start + resultPageSize.value)
})

const taskConfigSummary = computed(() => {
  const config = task.value?.config || {}
  const sheets = Array.isArray(config.sheets) ? config.sheets : []
  const firstSheet = sheets[0] || {}
  const parameters = Array.isArray(config.parameters) ? config.parameters : []
  const parameterPositions = config.parameter_positions || config.param_positions || []
  const checkPositions = config.check_positions || []
  const resultPositions = config.result_positions || []

  return {
    spreadsheetId: config.spreadsheet_id || firstSheet.spreadsheet_id || '-',
    sheetName: config.sheet_name || firstSheet.sheet_name || '-',
    title: config.title || config.spreadsheet_title || firstSheet.title || '-',
    token: config.token_id ? `ID ${config.token_id}` : config.token_type || '-',
    proxy: config.proxy_url || '-',
    parameterGroups: parameters.length || 0,
    positionSummary: `参数 ${parameterPositions.length} / 检查 ${checkPositions.length} / 结果 ${resultPositions.length}`,
    extraSummary:
      [
        config.market_type ? `市场 ${config.market_type}` : null,
        config.count_mode ? `模式 ${config.count_mode}` : null,
        sheets.length > 1 ? `${sheets.length} 组 Sheets` : null
      ]
        .filter(Boolean)
        .join('，') || '-'
  }
})

async function loadTask() {
  try {
    const res = await getTask(taskId)
    task.value = res.task || res
    resultSummary.value = res.result_summary || {}
  } catch {
    ElMessage.error('加载任务失败')
  }
}

async function loadLogs() {
  try {
    const res = await getTaskLogs(taskId)
    logs.value = res.logs || []
    setTimeout(() => {
      if (logContainerRef.value) {
        logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
      }
    }, 50)
  } catch {}
}

async function loadResults() {
  try {
    const res = await getTaskResults(taskId)
    allResults.value = res.results || []
    if (activeTab.value === 'results') {
      await nextTick()
      await renderResultChart()
    }
  } catch {}
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadTask(), loadLogs(), loadResults()])
  } finally {
    loading.value = false
  }
}

function formatDurationValue(value) {
  if (value == null || value === '') return '-'
  if (typeof value === 'number') return `${value}s`
  return String(value)
}

function formatResultPreview(result) {
  if (result == null) return '-'
  if (typeof result === 'string') return result
  const text = JSON.stringify(result)
  return text.length > 120 ? `${text.slice(0, 120)}...` : text
}

function handleResultPageSizeChange() {
  resultPage.value = 1
}

function scrollResultsToTop() {
  nextTick(() => {
    resultChartRef.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  })
}

async function renderResultChart() {
  if (!resultChartRef.value) return
  try {
    const ChartLib = await loadChartJs()
    const labels = allResults.value.map((item) => item.step_index)
    if (resultChart) resultChart.destroy()
    resultChart = new ChartLib(resultChartRef.value.getContext('2d'), {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: '成功',
            data: allResults.value.map((item) => (item.success ? 1 : 0)),
            borderColor: '#67c23a',
            backgroundColor: 'rgba(103,194,58,0.12)',
            fill: true,
            tension: 0.3
          },
          {
            label: '失败',
            data: allResults.value.map((item) => (item.success ? 0 : 1)),
            borderColor: '#f56c6c',
            backgroundColor: 'rgba(245,108,108,0.08)',
            fill: true,
            tension: 0.3
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'top' } },
        scales: {
          y: {
            beginAtZero: true,
            suggestedMax: 1
          }
        }
      }
    })
  } catch {}
}

async function checkStatus() {
  try {
    const res = await apiCheckStatus(taskId)
    ElMessage.info(`状态: ${res.status || '未知'}`)
    loadTask()
  } catch {
    ElMessage.error('检查状态失败')
  }
}

async function handleCancel() {
  await ElMessageBox.confirm('确定要停止这个任务吗？', '确认停止', { type: 'warning' })
  await cancelTask(taskId)
  ElMessage.success('已发送停止请求')
  loadTask()
}

async function handleRestart(cmd) {
  if (cmd === 'create') {
    router.push(`/task/create?restart_task_id=${taskId}`)
    return
  }
  await restartTask(taskId, { resume_from_checkpoint: cmd === 'resume' })
  ElMessage.success(cmd === 'resume' ? '任务已从断点重启' : '任务已从头重启')
  loadAll()
}

function viewResult(row) {
  currentResult.value = row
  resultDrawerVisible.value = true
}

watch(resultFilter, () => {
  resultPage.value = 1
})

watch(activeTab, async (tab) => {
  if (tab === 'results' && allResults.value.length) {
    await nextTick()
    await renderResultChart()
  }
})

usePolling(
  async () => {
    await loadTask()
    await loadLogs()

    if (activeTab.value === 'results') {
      await loadResults()
    }
  },
  {
    interval: 5000,
    immediate: false,
    isActive: () => task.value?.status === 'running' || task.value?.status === 'pending',
  }
)

onMounted(() => {
  void loadAll()
})

onUnmounted(() => {
  if (resultChart) resultChart.destroy()
})
</script>

<style scoped>
.task-detail-page__metrics {
  margin-bottom: 16px;
}

.task-detail-page__metric-col,
.task-detail-page__config-col {
  margin-bottom: 12px;
}

.task-detail-page__metric-card {
  height: 100%;
}

.task-detail-page__error-text {
  color: #dc2626;
  font-size: 12px;
}

.task-detail-page__hero {
  height: 100%;
}

.task-detail-page__hero-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.task-detail-page__hero-stat {
  padding: 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.08);
  text-align: center;
}

.task-detail-page__hero-value {
  font-size: 28px;
  font-weight: 700;
  color: #fff;
}

.task-detail-page__hero-label,
.task-detail-page__hero-foot {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
}

.task-detail-page__hero-progress {
  margin-top: 16px;
}

.task-detail-page__hero-foot {
  margin-top: 6px;
  text-align: center;
}

.task-detail-page__log-panel {
  height: 500px;
  overflow-y: auto;
  padding: 12px 14px;
  border-radius: 18px;
  background: #0b1220;
  color: #dbeafe;
  font-family: 'Fira Code', monospace;
  font-size: 13px;
  line-height: 1.6;
}

.task-detail-page__log-empty {
  padding-top: 120px;
}

.task-detail-page__results-head {
  margin-bottom: 12px;
}

.task-detail-page__chart-card {
  margin-bottom: 12px;
}

.task-detail-page__chart-title {
  margin-bottom: 10px;
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.task-detail-page__chart-wrap {
  height: 240px;
}

.task-detail-page__table {
  margin-top: 12px;
}

.task-detail-page__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.task-detail-page__config-grid {
  margin-bottom: 12px;
}

.task-detail-page__config-card {
  height: 100%;
}

.task-detail-page__config-code {
  max-height: 500px;
  margin: 0;
  overflow: auto;
}

.task-detail-page__drawer-body {
  display: grid;
  gap: 16px;
}

.task-detail-page__drawer-section {
  display: grid;
  gap: 8px;
}

.task-detail-page__drawer-code {
  max-height: 250px;
  margin: 0;
  overflow: auto;
}

.task-detail-page__error-block {
  max-height: 250px;
  margin: 0;
  overflow: auto;
  padding: 12px;
  border-radius: 12px;
  background: #fef2f2;
  color: #dc2626;
  font-family: 'Fira Code', monospace;
  font-size: 12px;
  line-height: 1.6;
}

.log-line {
  white-space: pre-wrap;
  word-break: break-all;
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
</style>
