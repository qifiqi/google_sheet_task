<template>
  <div class="app-page backtest-detail-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Backtest Monitor</div>
        <h2 class="page-title">回测任务详情</h2>
        <p class="page-description">对齐旧版结果结构，区分 C3 参数汇总与 C5/C4 结果列表，并保留日志与配置查看能力。</p>
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
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button class="page-back-button" @click="$router.push('/backtest/list')">返回列表</el-button>
      </div>
    </div>

    <div v-loading="loading">
      <el-row v-if="task" :gutter="16" class="backtest-detail-page__metrics">
        <el-col :xs="24" :md="8" class="backtest-detail-page__metric-col">
          <el-card shadow="never" class="page-section backtest-detail-page__metric-card">
            <div class="section-heading">
              <h3 class="section-title section-title--muted">基础执行信息</h3>
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

        <el-col :xs="24" :md="8" class="backtest-detail-page__metric-col">
          <el-card shadow="never" class="page-section backtest-detail-page__metric-card">
            <div class="section-heading">
              <h3 class="section-title section-title--muted">时间信息</h3>
            </div>
            <el-descriptions :column="1" size="small">
              <el-descriptions-item label="创建时间">{{ task.created_at || '-' }}</el-descriptions-item>
              <el-descriptions-item label="开始时间">{{ task.start_time || '-' }}</el-descriptions-item>
              <el-descriptions-item label="结束时间">{{ task.end_time || '-' }}</el-descriptions-item>
              <el-descriptions-item label="执行时长">
                {{ task.duration_seconds != null ? `${task.duration_seconds}s` : '-' }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>

        <el-col :xs="24" :md="8" class="backtest-detail-page__metric-col">
          <div class="hero-panel backtest-detail-page__hero">
            <div class="hero-panel__eyebrow">Execution Summary</div>
            <div class="backtest-detail-page__hero-stats">
              <div class="backtest-detail-page__hero-stat">
                <div class="backtest-detail-page__hero-value">{{ summary.success_count ?? 0 }}</div>
                <div class="backtest-detail-page__hero-label">成功</div>
              </div>
              <div class="backtest-detail-page__hero-stat">
                <div class="backtest-detail-page__hero-value">{{ summary.failed_count ?? 0 }}</div>
                <div class="backtest-detail-page__hero-label">失败</div>
              </div>
            </div>
            <div class="backtest-detail-page__hero-foot">结果模式：{{ modelVersion.toUpperCase() }}</div>
          </div>
        </el-col>
      </el-row>

      <div v-if="task" class="page-section">
        <div class="action-bar backtest-detail-page__jump-bar">
          <el-button @click="$router.push(`/backtest/${taskId}/global-preview`)">全局预览页</el-button>
          <el-button @click="$router.push(`/backtest/${taskId}/result`)">回测结果</el-button>
        </div>
      </div>

      <el-card v-if="task" shadow="never" class="page-section">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="任务日志" name="logs">
            <div ref="logContainerRef" class="backtest-detail-page__log-panel">
              <div v-if="!logs.length" class="panel-note panel-note--center backtest-detail-page__log-empty">暂无日志</div>
              <div v-for="(log, index) in logs" :key="index" :class="['log-line', `log-${log.level}`]">
                [{{ log.timestamp }}] [{{ (log.level || 'info').toUpperCase() }}] {{ log.message }}
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="执行结果" name="results">
            <div v-if="modelVersion === 'c3'">
              <div class="section-heading backtest-detail-page__results-head">
                <div>
                  <h3 class="section-title section-title--muted">参数汇总表</h3>
                  <div class="panel-note">
                    共 {{ c3SummaryMeta.row_count || 0 }} 行，{{ c3SummaryMeta.parameter_group_count || 0 }} 组参数
                  </div>
                </div>
              </div>

              <div class="backtest-detail-page__summary-wrap">
                <table class="backtest-detail-page__summary-table">
                  <thead>
                    <tr>
                      <th v-for="field in c3ParameterFields" :key="field.key">{{ field.label }}</th>
                      <th>年份</th>
                      <th>return%</th>
                      <th>index%</th>
                      <th class="backtest-detail-page__summary-highlight">beats Index%</th>
                      <th>strat max dd%</th>
                      <th>index max dd%</th>
                      <th>dd beats%</th>
                      <th>fee%</th>
                      <th>year rate%</th>
                      <th>index sharpe</th>
                      <th>strategy sharpe</th>
                      <th>区间</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-if="!c3SummaryRows.length">
                      <td :colspan="c3SummaryColspan" class="panel-note panel-note--center backtest-detail-page__empty-cell">
                        暂无参数汇总数据
                      </td>
                    </tr>
                    <tr v-for="(row, index) in c3SummaryRows" :key="`${row.task_result_id}-${index}`">
                      <td
                        v-for="field in c3ParameterFields"
                        :key="field.key"
                        class="backtest-detail-page__summary-parameter"
                      >
                        {{ row[field.key] ?? '-' }}
                      </td>
                      <td class="backtest-detail-page__summary-parameter">{{ row.year || '-' }}</td>
                      <td :class="metricClass(row.strategy_return)">{{ formatPercent(row.strategy_return) }}</td>
                      <td :class="metricClass(row.index_return)">{{ formatPercent(row.index_return) }}</td>
                      <td :class="['backtest-detail-page__summary-highlight', metricClass(row.beats_index)]">
                        {{ formatPercent(row.beats_index) }}
                      </td>
                      <td class="backtest-detail-page__summary-danger">{{ formatPercent(row.strategy_max_drawdown) }}</td>
                      <td class="backtest-detail-page__summary-danger">{{ formatPercent(row.index_max_drawdown) }}</td>
                      <td :class="metricClass(row.drawdown_beats)">{{ formatPercent(row.drawdown_beats) }}</td>
                      <td>{{ formatPercent(row.fee_total) }}</td>
                      <td>{{ formatPercent(row.year_rate) }}</td>
                      <td :class="metricClass(row.index_monthly_sharpe)">{{ formatNumber(row.index_monthly_sharpe) }}</td>
                      <td :class="metricClass(row.strategy_monthly_sharpe)">{{ formatNumber(row.strategy_monthly_sharpe) }}</td>
                      <td>{{ row.date_range || row.source_window || '-' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div v-else>
              <div class="section-heading backtest-detail-page__results-head">
                <div>
                  <h3 class="section-title section-title--muted">回测生成结果</h3>
                  <div class="panel-note">沿用旧版结果列表结构，重点展示结果 ID、执行参数、状态和时间。</div>
                </div>
              </div>

              <el-table :data="results" stripe class="backtest-detail-page__result-table">
                <el-table-column prop="id" label="结果 ID" min-width="180">
                  <template #default="{ row }">
                    <span class="font-mono">{{ row.id }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="执行参数" min-width="340">
                  <template #default="{ row }">
                    <div class="result-param-summary">
                      <div class="result-param-main">
                        <span
                          v-for="chip in buildPrimaryParameterChips(row.parameters)"
                          :key="chip.label"
                          class="result-param-chip"
                        >
                          <strong>{{ chip.label }}</strong>
                          <span>{{ chip.value }}</span>
                        </span>
                        <span v-if="!buildPrimaryParameterChips(row.parameters).length" class="panel-note">-</span>
                      </div>
                      <div class="result-param-detail">
                        <span
                          v-for="chip in buildExtraParameterChips(row.parameters)"
                          :key="chip.key"
                          class="result-param-chip"
                        >
                          <strong>{{ chip.label }}</strong>
                          <span>{{ chip.value }}</span>
                        </span>
                      </div>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="90">
                  <template #default="{ row }">
                    <el-tag :type="row.success ? 'success' : 'danger'" size="small">
                      {{ row.success ? '成功' : '失败' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="timestamp" label="创建时间" width="170" show-overflow-tooltip />
                <el-table-column label="操作" width="100">
                  <template #default="{ row }">
                    <el-button link type="primary" @click="viewResult(row)">查看结果</el-button>
                  </template>
                </el-table-column>
              </el-table>

              <div class="backtest-detail-page__pagination">
                <el-pagination
                  v-model:current-page="resultPage"
                  v-model:page-size="resultPageSize"
                  :total="resultTotal"
                  layout="total, prev, pager, next"
                  @current-change="loadResults"
                />
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="任务配置" name="config">
            <div class="backtest-detail-page__config-grid">
              <div class="sub-card backtest-detail-page__config-card">
                <div class="backtest-detail-page__card-title">输入参数</div>
                <div v-if="configHeaders.length && configRows.length" class="backtest-detail-page__param-table-wrap">
                  <table class="backtest-detail-page__param-table">
                    <thead>
                      <tr>
                        <th v-for="(header, index) in configHeaders" :key="`${header}-${index}`">{{ header }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, rowIndex) in configRows" :key="rowIndex">
                        <td v-for="(cell, cellIndex) in row" :key="`${rowIndex}-${cellIndex}`">{{ cell }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-else class="panel-note">当前任务没有结构化参数表。</div>
              </div>

              <div class="sub-card backtest-detail-page__config-card">
                <div class="backtest-detail-page__card-title">完整配置</div>
                <pre class="code-block backtest-detail-page__config-code">{{ JSON.stringify(task.config || {}, null, 2) }}</pre>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </div>

    <el-drawer v-model="resultDrawerVisible" title="结果详情" :size="isMobile ? '100%' : '560px'">
      <div v-if="currentResult" class="backtest-detail-page__drawer-body">
        <div class="backtest-detail-page__drawer-section">
          <div class="backtest-detail-page__card-title">参数信息</div>
          <pre class="code-block backtest-detail-page__drawer-code">{{ JSON.stringify(currentResult.parameters, null, 2) }}</pre>
        </div>
        <div class="backtest-detail-page__drawer-section">
          <div class="backtest-detail-page__card-title">执行结果</div>
          <pre class="code-block backtest-detail-page__drawer-code">{{ JSON.stringify(currentResult.result, null, 2) }}</pre>
        </div>
        <div v-if="currentResult.error_message" class="backtest-detail-page__drawer-section">
          <div class="backtest-detail-page__card-title">错误信息</div>
          <pre class="backtest-detail-page__error-block">{{ currentResult.error_message }}</pre>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import {
  getTaskResults,
  getTaskSummary
} from '@/api/backtest'
import {
  getTask,
  getTaskLogs,
  cancelTask,
  restartTask,
  checkTaskStatus as apiCheckStatus
} from '@/api/task'
import StatusTag from '@/components/StatusTag.vue'
import { useResponsive } from '@/composables/useResponsive'

const route = useRoute()
const router = useRouter()
const { isMobile } = useResponsive()

const taskId = route.params.id
const task = ref(null)
const logs = ref([])
const results = ref([])
const summary = ref({})
const loading = ref(false)
const activeTab = ref('logs')
const logContainerRef = ref()
const resultPage = ref(1)
const resultPageSize = ref(20)
const resultTotal = ref(0)
const resultDrawerVisible = ref(false)
const currentResult = ref(null)
const c3ParameterFields = ref([])
const c3SummaryRows = ref([])
const c3SummaryMeta = ref({})
let pollTimer = null

const modelVersion = computed(() => inferModelVersion(task.value?.config || {}))
const taskProgressPercent = computed(() => {
  if (!task.value?.total_steps) return 0
  return Math.min(100, Math.round(((task.value.current_step || 0) / task.value.total_steps) * 100))
})

const c3SummaryColspan = computed(() => c3ParameterFields.value.length + 9)

const configHeaders = computed(() => {
  const config = task.value?.config || {}
  return Array.isArray(config.headers) ? config.headers : []
})

const configRows = computed(() => {
  const config = task.value?.config || {}
  return Array.isArray(config.rows) ? config.rows : []
})

function inferModelVersion(config) {
  const sheet = config?.sheet || {}
  const title = String(sheet.title || config?.title || '').toUpperCase()
  if (title.includes('C5') || title.includes('C4')) return 'c5'
  const parameters = Array.isArray(config?.parameters) ? config.parameters : []
  const firstRow = Array.isArray(parameters[0]) ? parameters[0] : []
  return firstRow.length === 2 ? 'c5' : 'c3'
}

function normalizeParamObject(parameters) {
  if (!parameters) return null
  if (typeof parameters === 'string') {
    try {
      return JSON.parse(parameters)
    } catch {
      return parameters
    }
  }
  return parameters
}

function compactValue(value, max = 36) {
  if (value === null || value === undefined || value === '') return '-'
  const text = typeof value === 'object' ? JSON.stringify(value) : String(value)
  return text.length > max ? `${text.slice(0, max)}...` : text
}

function buildPrimaryParameterChips(parameters) {
  const payload = normalizeParamObject(parameters)
  if (!payload || Array.isArray(payload) || typeof payload !== 'object') return []

  const chips = []
  if (payload.stock_code) chips.push({ label: '股票', value: compactValue(payload.stock_code, 18) })
  if (payload.year !== undefined && payload.year !== null && payload.year !== '') {
    chips.push({ label: '年份', value: compactValue(payload.year, 18) })
  }
  if (payload.Kline_key !== undefined && payload.Kline_key !== null && payload.Kline_key !== '') {
    chips.push({ label: 'K线键', value: compactValue(payload.Kline_key, 18) })
  }
  if (Array.isArray(payload.kline) && payload.kline.length) {
    const first = payload.kline[0]?.stock_date || '-'
    const last = payload.kline[payload.kline.length - 1]?.stock_date || '-'
    chips.push({ label: 'K线', value: `${payload.kline.length}条 ${first} ~ ${last}` })
  }
  return chips
}

function buildExtraParameterChips(parameters) {
  const payload = normalizeParamObject(parameters)

  if (Array.isArray(payload)) {
    return payload.map((value, index) => ({
      key: `p-${index}`,
      label: `P${index + 1}`,
      value: compactValue(value, 24)
    }))
  }

  if (!payload || typeof payload !== 'object') {
    return payload == null
      ? []
      : [{ key: 'raw', label: '参数', value: compactValue(payload, 36) }]
  }

  const chips = []
  if (Array.isArray(payload.parameter)) {
    payload.parameter.forEach((value, index) => {
      chips.push({
        key: `parameter-${index}`,
        label: `P${index + 1}`,
        value: compactValue(value, 24)
      })
    })
  }

  Object.entries(payload)
    .filter(([key]) => !['stock_code', 'year', 'Kline_key', 'kline', 'parameter'].includes(key))
    .forEach(([key, value]) => {
      chips.push({
        key,
        label: key,
        value: compactValue(value, 32)
      })
    })

  return chips
}

function formatPercent(value) {
  if (value == null || value === '') return '-'
  if (typeof value === 'number') return `${(value * 100).toFixed(2)}%`
  return String(value)
}

function formatNumber(value) {
  if (value == null || value === '') return '-'
  if (typeof value === 'number') return value.toFixed(2).replace(/\.?0+$/, '')
  return String(value)
}

function metricClass(value) {
  if (typeof value !== 'number') return ''
  if (value > 0) return 'backtest-detail-page__metric-positive'
  if (value < 0) return 'backtest-detail-page__metric-negative'
  return ''
}

async function loadTask() {
  try {
    const res = await getTask(taskId)
    task.value = res.task || res
    summary.value = res.result_summary || {}
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
  if (modelVersion.value === 'c3') {
    await loadC3Summary()
    return
  }

  try {
    const res = await getTaskResults(taskId, { page: resultPage.value, per_page: resultPageSize.value })
    results.value = res.results || []
    resultTotal.value = res.total || res.pagination?.total || 0
  } catch {}
}

async function loadC3Summary() {
  try {
    const res = await getTaskSummary(taskId)
    c3ParameterFields.value = res.parameter_fields || []
    c3SummaryRows.value = res.rows || []
    c3SummaryMeta.value = res.summary || {}
  } catch {
    c3ParameterFields.value = []
    c3SummaryRows.value = []
    c3SummaryMeta.value = {}
  }
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
  await restartTask(taskId, cmd === 'resume' ? 'resume' : 'fresh')
  ElMessage.success('任务重启成功')
  loadTask()
  loadResults()
}

function viewResult(row) {
  currentResult.value = row
  resultDrawerVisible.value = true
}

onMounted(() => {
  loading.value = true
  Promise.all([loadTask(), loadLogs()]).finally(async () => {
    await loadResults()
    loading.value = false
  })

  pollTimer = setInterval(() => {
    if (task.value?.status === 'running' || task.value?.status === 'pending') {
      loadTask()
      loadLogs()
    }
  }, 5000)
})

onUnmounted(() => clearInterval(pollTimer))
</script>

<style scoped>
.backtest-detail-page__metrics {
  margin-bottom: 16px;
}

.backtest-detail-page__metric-col {
  margin-bottom: 12px;
}

.backtest-detail-page__metric-card {
  height: 100%;
}

.backtest-detail-page__hero {
  height: 100%;
}

.backtest-detail-page__hero-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.backtest-detail-page__hero-stat {
  padding: 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.08);
  text-align: center;
}

.backtest-detail-page__hero-value {
  color: #fff;
  font-size: 28px;
  font-weight: 700;
}

.backtest-detail-page__hero-label,
.backtest-detail-page__hero-foot {
  color: rgba(255, 255, 255, 0.76);
  font-size: 12px;
}

.backtest-detail-page__hero-foot {
  margin-top: 14px;
  text-align: center;
}

.backtest-detail-page__jump-bar {
  justify-content: flex-start;
}

.backtest-detail-page__log-panel {
  height: 320px;
  overflow-y: auto;
  overflow-x: auto;
  padding: 12px 14px;
  border-radius: 14px;
  background: #0b1220;
  color: #dbeafe;
  font-family: 'Fira Code', monospace;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre;
  word-break: normal;
}

.backtest-detail-page__log-empty {
  padding-top: 120px;
}

.backtest-detail-page__results-head {
  margin-bottom: 12px;
}

.backtest-detail-page__summary-wrap {
  overflow: auto;
}

.backtest-detail-page__summary-table {
  min-width: 1680px;
  width: 100%;
  border-collapse: collapse;
}

.backtest-detail-page__summary-table th,
.backtest-detail-page__summary-table td {
  padding: 10px 12px;
  border: 1px solid rgba(30, 64, 175, 0.12);
  text-align: center;
  vertical-align: middle;
  white-space: nowrap;
}

.backtest-detail-page__summary-table thead th {
  background: rgba(232, 239, 250, 0.72);
  font-weight: 700;
}

.backtest-detail-page__summary-parameter {
  background: rgba(243, 246, 252, 0.96);
  font-weight: 600;
}

.backtest-detail-page__summary-highlight {
  background: linear-gradient(180deg, #fff3bf, #ffe69c);
}

.backtest-detail-page__summary-danger {
  color: #dc2626;
}

.backtest-detail-page__empty-cell {
  padding: 32px 0;
}

.backtest-detail-page__metric-positive {
  color: #15803d;
}

.backtest-detail-page__metric-negative {
  color: #c2410c;
}

.backtest-detail-page__result-table {
  margin-top: 4px;
}

.backtest-detail-page__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.result-param-summary {
  display: grid;
  gap: 8px;
}

.result-param-main,
.result-param-detail {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.result-param-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid rgba(30, 64, 175, 0.16);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
  font-size: 13px;
  line-height: 1.35;
}

.result-param-chip strong {
  color: var(--app-text);
  font-weight: 700;
}

.backtest-detail-page__config-grid {
  display: grid;
  gap: 12px;
}

.backtest-detail-page__config-card {
  display: grid;
  gap: 10px;
}

.backtest-detail-page__card-title {
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.backtest-detail-page__param-table-wrap {
  overflow: auto;
}

.backtest-detail-page__param-table {
  width: 100%;
  min-width: 720px;
  border-collapse: collapse;
}

.backtest-detail-page__param-table th,
.backtest-detail-page__param-table td {
  padding: 10px 12px;
  border: 1px solid rgba(30, 64, 175, 0.12);
  text-align: left;
}

.backtest-detail-page__param-table th {
  background: rgba(232, 239, 250, 0.72);
}

.backtest-detail-page__config-code {
  max-height: 500px;
  margin: 0;
  overflow: auto;
}

.backtest-detail-page__drawer-body {
  display: grid;
  gap: 16px;
}

.backtest-detail-page__drawer-section {
  display: grid;
  gap: 8px;
}

.backtest-detail-page__drawer-code {
  max-height: 250px;
  margin: 0;
  overflow: auto;
}

.backtest-detail-page__error-block {
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
  white-space: pre;
  word-break: normal;
  margin-bottom: 4px;
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
