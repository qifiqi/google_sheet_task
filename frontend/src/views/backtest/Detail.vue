<template>
  <div class="app-page backtest-detail-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Backtest Monitor</div>
        <h2 class="page-title">回测任务详情</h2>
        <p class="page-description">对齐旧版结果结构，区分 C3 参数汇总与 C5/C4 结果列表，并保留日志与配置查看能力。</p>
      </div>
      <div class="page-toolbar__actions">
        <el-button :disabled="taskActionInProgress" @click="checkStatus">检查状态</el-button>
        <el-button
          v-if="canStopTask"
          type="warning"
          :disabled="taskActionInProgress"
          @click="handleStopTask"
        >停止任务</el-button>
        <el-dropdown v-if="task" @command="handleRestart">
          <el-button type="success" :disabled="taskActionInProgress">
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
        <el-button class="page-back-button" @click="$router.push({ path: '/backtest/list', query: backListQuery })">返回列表</el-button>
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
          <el-button @click="$router.push({ path: `/backtest/${taskId}/global-preview`, query: pagingLink() })">全局预览页</el-button>
          <el-button @click="refreshPageData()">刷新详情与日志</el-button>
        </div>
      </div>

      <el-card v-if="task" shadow="never" class="page-section">
        <el-tabs v-model="activeTab">
          <el-tab-pane name="logs">
            <template #label>
              <span>任务日志</span>
            </template>
            <div class="backtest-detail-page__log-tools">
              <span class="panel-note">最近刷新：{{ logLastUpdated || '-' }}</span>
              <el-button size="small" @click="refreshPageData()">刷新日志</el-button>
            </div>
            <div ref="logContainerRef" class="backtest-detail-page__log-panel" @scroll="onLogScroll">
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
                    共 {{ c3SummaryMeta.row_count || 0 }} 行，{{ c3SummaryMeta.parameter_group_count || 0 }} 组参数。
                    当前已显示 {{ selectedC3MetricDefs.length }} 个数据项，可随时切换。
                  </div>
                </div>
                <div class="section-actions">
                  <el-button size="small" @click="copyTaskParameters">复制参数</el-button>
                  <el-button size="small" type="primary" plain @click="c3MetricDialogVisible = true">选择数据项</el-button>
                </div>
              </div>

              <div class="backtest-detail-page__summary-wrap">
                <table class="backtest-detail-page__summary-table">
                  <thead>
                    <tr>
                      <th>X Multiplier</th>
                      <th>tp1</th>
                      <th>tp2</th>
                      <th>nl</th>
                      <th>if</th>
                      <th>ywfs</th>
                      <th>ywfb</th>
                      <th>年份</th>
                      <th
                        v-for="metric in selectedC3MetricDefs"
                        :key="metric.key"
                        :class="{ 'backtest-detail-page__summary-highlight': metric.highlight }"
                      >{{ metric.label }}</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-if="!c3SummaryRows.length">
                      <td :colspan="c3SummaryColspan" class="panel-note panel-note--center backtest-detail-page__empty-cell">
                        暂无参数汇总数据
                      </td>
                    </tr>
                    <template v-for="(group, groupIndex) in c3SummaryGroups" :key="group.key">
                      <tr v-for="(row, rowIndex) in group.rows" :key="`${row.task_result_id}-${rowIndex}`">
                        <template v-if="rowIndex === 0">
                          <td
                            v-for="paramKey in C3_SUMMARY_PARAM_KEYS"
                            :key="paramKey"
                            :rowspan="group.rows.length"
                            class="backtest-detail-page__summary-parameter"
                          >{{ row[paramKey] ?? '' }}</td>
                        </template>
                        <td class="backtest-detail-page__summary-year">{{ row.year ?? '' }}</td>
                        <td
                          v-for="metric in selectedC3MetricDefs"
                          :key="metric.key"
                          :class="c3MetricCellClass(metric, row)"
                        >{{ formatC3MetricValue(metric, row) }}</td>
                        <td class="backtest-detail-page__summary-action">
                          <el-button
                            link
                            type="primary"
                            size="small"
                            @click="$router.push({ path: `/backtest/${row.task_result_id}/result`, query: pagingLink() })"
                          >查看结果</el-button>
                        </td>
                      </tr>
                    </template>
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
                    <el-button link type="primary" @click="viewResultPage(row)">查看结果</el-button>
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
                <div class="backtest-detail-page__card-title">任务配置</div>
                <div class="backtest-detail-page__config-items">
                  <div v-for="item in configDisplayItems" :key="item.label" class="backtest-detail-page__config-item">
                    <div class="backtest-detail-page__config-label">{{ item.label }}</div>
                    <div class="backtest-detail-page__config-value">
                      <code v-if="isComplexValue(item.value)">{{ JSON.stringify(item.value) }}</code>
                      <span v-else>{{ item.value ?? '-' }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div class="sub-card backtest-detail-page__config-card">
                <div class="backtest-detail-page__card-title">输入参数</div>
                <div v-if="configParameters.length" class="backtest-detail-page__param-table-wrap">
                  <table class="backtest-detail-page__param-table">
                    <thead>
                      <tr>
                        <th>参数组</th>
                        <th v-for="(label, index) in parameterHeadLabels" :key="index">{{ label }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(group, groupIndex) in configParameters" :key="groupIndex">
                        <td class="backtest-detail-page__param-group">第 {{ groupIndex + 1 }} 组</td>
                        <td v-for="cellIndex in parameterColumnCount" :key="cellIndex">
                          {{ renderConfigCellValue((Array.isArray(group) ? group : [group])[cellIndex - 1]) }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-else-if="configHeaders.length && configRows.length" class="backtest-detail-page__param-table-wrap">
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
                <div v-else class="panel-note">暂无参数配置</div>
                <div class="backtest-detail-page__copy-bar">
                  <el-button size="small" @click="copyTaskParameters">复制参数</el-button>
                </div>
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

    <el-dialog v-model="c3MetricDialogVisible" title="选择数据项" width="680px" top="6vh">
      <div class="panel-note" style="margin-bottom: 10px;">
        勾选后立即生效并记忆；共 {{ C3_SUMMARY_METRIC_DEFS.length }} 个数据项。
      </div>
      <div class="backtest-detail-page__metric-selector">
        <el-checkbox-group v-model="c3SelectedMetricKeys" @change="applyC3MetricSelection(c3SelectedMetricKeys)">
          <el-checkbox
            v-for="metric in C3_SUMMARY_METRIC_DEFS"
            :key="metric.key"
            :value="metric.key"
            :label="metric.label"
          >
            {{ metric.label }}
          </el-checkbox>
        </el-checkbox-group>
      </div>
      <template #footer>
        <div class="backtest-detail-page__batch-footer">
          <el-button size="small" @click="resetC3MetricSelection">恢复默认</el-button>
          <el-button type="primary" @click="c3MetricDialogVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listQueryFromRoute, initialResultPagination, paginationLinkQuery, writeJsonStorage, replaceQuery } from '@/utils/pageState'
import { formatDateTime } from '@/utils/format'
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

const route = useRoute()
const router = useRouter()

const taskId = route.params.id
const task = ref(null)
const logs = ref([])
const results = ref([])
const summary = ref({})
const loading = ref(false)
const activeTab = ref('logs')
const logContainerRef = ref()
const logLastUpdated = ref('')
let logStickToBottom = true
// 分页状态链（自静态版翻译）：回列表/跳结果/跳全局预览统一携带分页上下文
const LIST_PAGING_KEY = 'backtest_training:list_pagination'
const RESULT_PAGING_KEY = `backtest_training:task_results:${taskId}:pagination`
const listState = listQueryFromRoute(route.query, LIST_PAGING_KEY, 20)
const backListQuery = { page: String(listState.page), per_page: String(listState.perPage) }
const initialResultPaging = initialResultPagination(route.query, RESULT_PAGING_KEY, 10)
const resultPage = ref(initialResultPaging.page)
const resultPageSize = ref(initialResultPaging.perPage)

function pagingLink() {
  return paginationLinkQuery(listState, { page: resultPage.value, perPage: resultPageSize.value })
}
const resultTotal = ref(0)
const c3SummaryRows = ref([])
const c3SummaryMeta = ref({})
let pollTimer = null

// ---------- 模型推断（翻译自静态 detail.js inferModelVersion，含 C7 分支） ----------
function parseTaskConfig(rawConfig) {
  if (rawConfig && typeof rawConfig === 'object') return rawConfig
  if (typeof rawConfig === 'string' && rawConfig) {
    try {
      return JSON.parse(rawConfig)
    } catch {
      return {}
    }
  }
  return {}
}

function inferModelVersion(config, taskName = '') {
  const sheet = config && config.sheet ? config.sheet : {}
  const text = [
    config && config.model_version,
    taskName,
    config && config.title,
    sheet.title,
    sheet.sheet_name,
  ].filter(Boolean).join(' ').toUpperCase()
  if (text.includes('C7')) {
    return 'c7'
  }
  if (text.includes('C5') || text.includes('C4')) {
    return 'c5'
  }
  return 'c3'
}

const currentModelConfig = computed(() => parseTaskConfig(task.value?.config))
const modelVersion = computed(() => inferModelVersion(currentModelConfig.value, task.value?.name || ''))
const taskProgressPercent = computed(() => {
  if (!task.value?.total_steps) return 0
  return Math.min(100, Math.round(((task.value.current_step || 0) / task.value.total_steps) * 100))
})

// ---------- 行为对齐（pending 也可停止 / 操作互斥锁） ----------
const taskActionInProgress = ref(false)
const canStopTask = computed(() => task.value?.status === 'pending' || task.value?.status === 'running')

function withTaskActionLock(action) {
  if (taskActionInProgress.value) {
    ElMessage.warning('当前已有任务操作正在执行，请稍候')
    return Promise.resolve()
  }
  taskActionInProgress.value = true
  return Promise.resolve()
    .then(action)
    .catch((error) => {
      ElMessage.error(`${error.message || '未知错误'}`)
    })
    .finally(() => {
      taskActionInProgress.value = false
      loadTask()
    })
}

// ---------- C3 汇总：44 项指标定义（逐项照抄静态 C3_SUMMARY_METRIC_DEFS） ----------
const C3_SUMMARY_STORAGE_KEY = 'backtest_training:c3_summary_metric_keys'
const C3_SUMMARY_METRIC_DEFS = [
  { key: 'strategy_return', label: '策略收益%', format: 'percent', defaultSelected: true, signClass: true },
  { key: 'index_return', label: '指数收益%', format: 'percent', defaultSelected: true, signClass: true },
  { key: 'beats_index', label: '收益差%', format: 'percent', defaultSelected: true, signClass: true, highlight: true },
  { key: 'strategy_max_drawdown', label: '策略最大回撤%', format: 'drawdown', defaultSelected: true, danger: true },
  { key: 'index_max_drawdown', label: '指数最大回撤%', format: 'drawdown', defaultSelected: true, danger: true },
  { key: 'drawdown_beats', label: '回撤差%', format: 'percent', defaultSelected: true, signClass: true, highlight: true },
  { key: 'fee_pair', label: 'Fee total / annualized', format: 'feePair', defaultSelected: true },
  { key: 'year_rate', label: '年换手率%', format: 'percent', defaultSelected: true },
  { key: 'index_monthly_sharpe', label: '指数月夏普', format: 'number', defaultSelected: true, signClass: true },
  { key: 'strategy_monthly_sharpe', label: '策略月夏普', format: 'number', defaultSelected: true, signClass: true },
  { key: 'avg_abs_change', label: '日均abs(chg%)', format: 'percent', defaultSelected: true },
  { key: 'max_abs_change', label: 'MAX abs(chg%)', format: 'percent', defaultSelected: true },
  { key: 'avg_abs_stddev', label: '日均abs标准差', format: 'number', defaultSelected: true },
  { key: 'strategy_annualized', label: '策略年化收益%', format: 'percent', signClass: true },
  { key: 'index_annualized', label: '指数年化收益%', format: 'percent', signClass: true },
  { key: 'fee_total', label: 'Fee total%', format: 'percent' },
  { key: 'fee_annualized', label: 'Fee annualized%', format: 'percent' },
  { key: 'index_avg_monthly_return', label: '指数平均月收益%', format: 'percent', signClass: true },
  { key: 'strategy_avg_monthly_return', label: '策略平均月收益%', format: 'percent', signClass: true },
  { key: 'index_monthly_return_volatility', label: '指数月波动率%', format: 'percent' },
  { key: 'strategy_monthly_return_volatility', label: '策略月波动率%', format: 'percent' },
  { key: 'excess_annualized_return', label: '超额年化收益%', format: 'percent', signClass: true },
  { key: 'outperform_year', label: '跑赢年份%', format: 'percent', signClass: true },
  { key: 'monthly_excess_return_percentage', label: '月超额胜率%', format: 'percent', signClass: true },
  { key: 'avg_monthly_excess_return', label: '平均月超额%', format: 'percent', signClass: true },
  { key: 'monthly_excess_volatility', label: '月超额波动率%', format: 'percent' },
  { key: 'index_profit_annual', label: '指数盈利年份%', format: 'percent', signClass: true },
  { key: 'strategy_profit_annual', label: '策略盈利年份%', format: 'percent', signClass: true },
  { key: 'index_profit_monthly_percentage', label: '指数月盈利率%', format: 'percent', signClass: true },
  { key: 'strategy_profit_monthly_percentage', label: '策略月盈利率%', format: 'percent', signClass: true },
  { key: 'index_kama_ratio', label: '指数卡玛', format: 'number', signClass: true },
  { key: 'strategy_kama_ratio', label: '策略卡玛', format: 'number', signClass: true },
  { key: 'index_sortino_ratio', label: '指数索提诺', format: 'number', signClass: true },
  { key: 'strategy_sortino_ratio', label: '策略索提诺', format: 'number', signClass: true },
  { key: 'excess_sharpe', label: '超额夏普', format: 'number', signClass: true },
  { key: 'excess_sortino', label: '超额索提诺', format: 'number', signClass: true },
  { key: 'excess_drawdown_winning_rate', label: '超额回撤胜率%', format: 'percent', signClass: true },
  { key: 'index_maximum_number_of_backtest_repair_days', label: '指数最大修复天数', format: 'integer' },
  { key: 'strategy_maximum_number_of_backtest_repair_days', label: '策略最大修复天数', format: 'integer' },
  { key: 'excess_maximum_number_of_backtest_repair_days', label: '超额最大修复天数', format: 'integer' },
  { key: 'date_range', label: '结果区间', format: 'text' },
  { key: 'source_window', label: '运行窗口', format: 'text' },
  { key: 'timestamp', label: '结果时间', format: 'datetime' },
]
// 参数列分组键：commission + 7 个业务参数（与静态 buildSummaryGroupKey 一致）
const C3_SUMMARY_PARAM_KEYS = ['xm', 'dbbh1', 'dbbh2', 'zlxc', 'zsgz', 'ywf1', 'ywf2']
const C3_SUMMARY_GROUP_KEYS = ['commission', ...C3_SUMMARY_PARAM_KEYS]

const c3SelectedMetricKeys = ref([])
const c3MetricDialogVisible = ref(false)

function getDefaultC3MetricKeys() {
  return C3_SUMMARY_METRIC_DEFS
    .filter((item) => item.defaultSelected)
    .map((item) => item.key)
}

function getValidC3MetricKeys(metricKeys) {
  const validKeys = new Set(C3_SUMMARY_METRIC_DEFS.map((item) => item.key))
  return (Array.isArray(metricKeys) ? metricKeys : []).filter((key) => validKeys.has(key))
}

function loadSavedC3MetricKeys() {
  try {
    const raw = localStorage.getItem(C3_SUMMARY_STORAGE_KEY)
    if (!raw) {
      return []
    }
    return getValidC3MetricKeys(JSON.parse(raw))
  } catch {
    return []
  }
}

function ensureC3MetricSelection() {
  if (c3SelectedMetricKeys.value.length) {
    return
  }
  const savedKeys = loadSavedC3MetricKeys()
  c3SelectedMetricKeys.value = savedKeys.length ? savedKeys : getDefaultC3MetricKeys()
}

function applyC3MetricSelection(metricKeys) {
  // 勾选即时生效：校验 + 持久化（非法键静默过滤）
  c3SelectedMetricKeys.value = getValidC3MetricKeys(metricKeys)
  try {
    localStorage.setItem(C3_SUMMARY_STORAGE_KEY, JSON.stringify(c3SelectedMetricKeys.value))
  } catch {
    // 存储失败时保留当前内存中的选择
  }
}

function resetC3MetricSelection() {
  applyC3MetricSelection(getDefaultC3MetricKeys())
}

const selectedC3MetricDefs = computed(() => {
  ensureC3MetricSelection()
  const selectedKeys = new Set(c3SelectedMetricKeys.value)
  return C3_SUMMARY_METRIC_DEFS.filter((item) => selectedKeys.has(item.key))
})

const c3SummaryColspan = computed(() => 9 + selectedC3MetricDefs.value.length)

// 按参数组合分组：commission..ywf2 相同的相邻行合并（rows 已按参数签名排序）
const c3SummaryGroups = computed(() => {
  const groups = []
  let currentGroup = null
  c3SummaryRows.value.forEach((row) => {
    const key = C3_SUMMARY_GROUP_KEYS.map((field) => row[field] ?? '').join('|')
    if (!currentGroup || currentGroup.key !== key) {
      currentGroup = { key, rows: [] }
      groups.push(currentGroup)
    }
    currentGroup.rows.push(row)
  })
  return groups
})

// ---------- C3 汇总单元格格式化（翻译自静态 format*Value） ----------
function formatPercentValue(value, digits = 2) {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'string') return value
  return `${(Number(value) * 100).toFixed(digits)}%`
}

function formatNumberValue(value, digits = 6) {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'string') return value
  return Number(value).toFixed(digits)
}

function formatIntegerValue(value) {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'string') return value
  return String(Math.round(Number(value)))
}

function formatFeeValue(totalValue, annualizedValue) {
  const totalText = formatPercentValue(totalValue)
  const annualizedText = formatPercentValue(annualizedValue)
  if (totalText && annualizedText) {
    return `${totalText} / ${annualizedText}`
  }
  return totalText || annualizedText || ''
}

function c3MetricCellClass(metricDef, row) {
  const classes = []
  if (metricDef.danger) {
    classes.push('backtest-detail-page__metric-danger')
  }
  if (metricDef.signClass) {
    const value = row[metricDef.key]
    if (value !== null && value !== undefined && value !== '' && typeof value !== 'string') {
      classes.push(Number(value) >= 0
        ? 'backtest-detail-page__metric-positive'
        : 'backtest-detail-page__metric-negative')
    }
  }
  return classes
}

function formatC3MetricValue(metricDef, row) {
  switch (metricDef.format) {
    case 'percent':
      return formatPercentValue(row[metricDef.key]) || '-'
    case 'drawdown':
      return formatPercentValue(row[metricDef.key]) || '-'
    case 'number':
      return formatNumberValue(row[metricDef.key]) || '-'
    case 'integer':
      return formatIntegerValue(row[metricDef.key]) || '-'
    case 'feePair':
      return formatFeeValue(row.fee_total, row.fee_annualized) || '-'
    case 'datetime':
      return row[metricDef.key] ? formatDateTime(row[metricDef.key]) : '-'
    case 'text':
    default:
      return row[metricDef.key] ?? '-'
  }
}

// ---------- 任务配置结构化展示（翻译自静态 renderTaskConfig 的 18 项字段） ----------
const KLINE_ADJUSTMENT_LABELS = { forward: '前复权', back: '后复权', none: '不复权' }
const PRICE_MODE_LABELS = {
  vwap_price: '加权平均价',
  kp_price: '开盘价',
  sp_price: '收盘价',
  ohlc_price: 'OHLC（开高低收）',
}

function formatConfigDisplayValue(value) {
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  if (Array.isArray(value)) {
    if (!value.length) {
      return '-'
    }
    return value.join(', ')
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

function isComplexValue(value) {
  return value !== null && typeof value === 'object'
}

const configDisplayItems = computed(() => {
  const config = { ...currentModelConfig.value, task_name: task.value?.name }
  const sheet = config.sheet && typeof config.sheet === 'object' ? config.sheet : {}
  return [
    { label: '股票代码', value: config.stock_code },
    { label: '股票名称', value: config.stock_name },
    { label: '市场类型', value: config.market_type },
    { label: 'K线复权', value: KLINE_ADJUSTMENT_LABELS[config.kline_adjustment] || config.kline_adjustment },
    { label: '价格模式', value: PRICE_MODE_LABELS[config.price_mode] || config.price_mode },
    { label: 'K线数据源', value: config.kline_data_source },
    { label: 'K线截至日期', value: config.end_date },
    { label: 'Spreadsheet ID', value: sheet.spreadsheet_id },
    { label: '工作表名称', value: sheet.sheet_name },
    { label: '表格标题', value: sheet.title },
    { label: 'C7 模型版本', value: sheet.c7_model_version },
    { label: 'Token ID', value: config.token_id },
    { label: 'Token 名称', value: config.token_name },
    { label: 'Token 类型', value: config.token_type },
    { label: 'Token 任务类型', value: config.token_task_type },
    { label: 'Token 文件', value: config.token_file },
    { label: '近 N 年', value: formatConfigDisplayValue(config.recent_years) },
    { label: '完整年份', value: formatConfigDisplayValue(config.full_years) },
  ]
})

// 输入参数表：config.parameters 为准（静态契约）；headers/rows 仅兼容旧 Vue 任务
const configParameters = computed(() => {
  const parameters = currentModelConfig.value.parameters
  return Array.isArray(parameters) ? parameters.filter((group) => Array.isArray(group) && group.length) : []
})

const parameterColumnCount = computed(() => (
  configParameters.value.reduce((max, group) => Math.max(max, Array.isArray(group) ? group.length : 0), 0)
))

const PARAMETER_FIELD_LABELS = {
  c7: ['X Multiplier (xm)', 'ML (ml)'],
  c5: ['X Multiplier (xm)', 'ML (ml)'],
  c3: ['Commission', 'X Multiplier', '单边保护1', '单边保护2', '中立限仓', '指数跟踪', '一窝蜂 smoothing', '一窝蜂 bordering'],
}

const parameterHeadLabels = computed(() => {
  const labels = PARAMETER_FIELD_LABELS[modelVersion.value] || []
  return Array.from({ length: parameterColumnCount.value }, (_, index) => labels[index] || `参数 ${index + 1}`)
})

function renderConfigCellValue(value) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const configHeaders = computed(() => {
  const config = currentModelConfig.value
  return Array.isArray(config.headers) ? config.headers : []
})

const configRows = computed(() => {
  const config = currentModelConfig.value
  return Array.isArray(config.rows) ? config.rows : []
})

// ---------- 复制参数（参数行 Tab 分隔写入剪贴板） ----------
async function writeClipboardText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  const ok = document.execCommand('copy')
  textarea.remove()
  if (!ok) {
    throw new Error('复制失败，请检查浏览器剪切板权限')
  }
}

async function copyTaskParameters() {
  try {
    const rows = Array.isArray(currentModelConfig.value.parameters) ? currentModelConfig.value.parameters : []
    const text = rows
      .filter((row) => Array.isArray(row) && row.some((value) => String(value ?? '').trim()))
      .map((row) => row.join('\t'))
      .join('\n')
    if (!text) {
      throw new Error('当前任务没有可复制的参数')
    }
    await writeClipboardText(text)
    ElMessage.success('参数已复制，可直接粘贴到单产品回测创建页')
  } catch (error) {
    ElMessage.error(error.message || '复制参数失败')
  }
}

// ---------- 结果参数 chips（沿用原实现） ----------
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

// ---------- 数据加载 ----------
async function loadTask() {
  try {
    const res = await getTask(taskId)
    task.value = res.task || res
  } catch (error) {
    ElMessage.error(`加载任务失败：${error.message || '未知错误'}`)
  }
}

async function loadLogs() {
  try {
    const res = await getTaskLogs(taskId)
    logs.value = res.logs || []
    logLastUpdated.value = formatDateTime(new Date().toISOString())
    // 仅当滚动条原本就在近底部时才跟随滚底（与静态版 wasNearBottom 行为一致）
    if (logStickToBottom) {
      await nextTick()
      const container = logContainerRef.value
      if (container) {
        container.scrollTop = container.scrollHeight
      }
    }
  } catch {}
}

function onLogScroll() {
  const container = logContainerRef.value
  if (!container) return
  logStickToBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 12
}

async function loadResults() {
  if (modelVersion.value === 'c3') {
    await loadC3Summary()
    return
  }

  try {
    const res = await getTaskResults(taskId, { page: resultPage.value, per_page: resultPageSize.value })
    results.value = res.items || []
    resultTotal.value = res.total || 0
    writeJsonStorage(RESULT_PAGING_KEY, { page: resultPage.value, per_page: resultPageSize.value })
    replaceQuery(router, route, { result_page: String(resultPage.value), result_per_page: String(resultPageSize.value) })
    const total = resultTotal.value
    const successCount = results.value.filter((item) => item.success).length
    summary.value = {
      success_count: successCount,
      failed_count: Math.max(total - successCount, 0),
    }
  } catch {}
}

async function loadC3Summary() {
  try {
    const res = await getTaskSummary(taskId)
    c3SummaryRows.value = res.rows || []
    c3SummaryMeta.value = res.summary || {}
  } catch {
    c3SummaryRows.value = []
    c3SummaryMeta.value = {}
  }
}

async function checkStatus() {
  try {
    const res = await apiCheckStatus(taskId)
    ElMessage.info(`状态: ${res.db_status || '未知'}`)
    loadTask()
  } catch (error) {
    ElMessage.error(`检查状态失败：${error.message || '未知错误'}`)
  }
}

async function handleStopTask() {
  try {
    await ElMessageBox.confirm('确认停止当前回测任务吗？已完成的结果会保留，任务状态会变为已取消。', '确认停止', { type: 'warning' })
  } catch {
    return
  }

  await withTaskActionLock(async () => {
    const res = await cancelTask(taskId)
    ElMessage.success(res.message || '任务已停止')
  })
}

async function handleRestart(cmd) {
  const isResume = cmd === 'resume'
  try {
    await ElMessageBox.confirm(
      isResume
        ? '确认按断点继续重启当前任务吗？系统会尽量从当前进度恢复执行。'
        : '确认重头开始当前任务吗？这会清空当前任务已有结果并从第 1 步重新执行。',
      isResume ? '断点重启' : '重头开始',
      { type: 'warning' },
    )
  } catch {
    return
  }

  await withTaskActionLock(async () => {
    // 后端 TaskRestartSchema 只认 resume_from_checkpoint 布尔
    const res = await restartTask(taskId, { resume_from_checkpoint: isResume })
    ElMessage.success(res.message || (isResume ? '任务已按断点重启' : '任务已重头开始'))
  })
}

function viewResultPage(row) {
  router.push({ path: `/backtest/${row.id}/result`, query: pagingLink() })
}

function refreshPageData(showTip = true) {
  loadTask()
  loadLogs()
  if (showTip) {
    ElMessage.info('详情与日志已刷新')
  }
}

onMounted(() => {
  ensureC3MetricSelection()
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

.backtest-detail-page__log-tools {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-bottom: 8px;
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

.backtest-detail-page__summary-year {
  font-weight: 600;
}

.backtest-detail-page__summary-highlight {
  background: linear-gradient(180deg, #fff3bf, #ffe69c);
}

.backtest-detail-page__summary-action {
  text-align: right;
}

.backtest-detail-page__metric-danger {
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

.backtest-detail-page__config-items {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 8px;
}

.backtest-detail-page__config-item {
  padding: 8px 12px;
  border: 1px solid rgba(30, 64, 175, 0.12);
  border-radius: 12px;
  background: rgba(243, 246, 252, 0.6);
}

.backtest-detail-page__config-label {
  color: #64748b;
  font-size: 12px;
}

.backtest-detail-page__config-value {
  margin-top: 2px;
  color: var(--app-text);
  font-size: 13px;
  font-weight: 600;
  word-break: break-all;
}

.backtest-detail-page__copy-bar {
  display: flex;
  justify-content: flex-end;
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

.backtest-detail-page__param-group {
  font-weight: 600;
}

.backtest-detail-page__config-code {
  max-height: 500px;
  margin: 0;
  overflow: auto;
}

.backtest-detail-page__metric-selector {
  max-height: 52vh;
  overflow-y: auto;
}

.backtest-detail-page__batch-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
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
