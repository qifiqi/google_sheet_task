<template>
  <div class="app-page task-detail-page">
    <PageToolbar
      eyebrow="Task Monitor"
      title="任务详情"
      description="查看任务状态、执行日志、结果趋势和当前配置，支持停止与重启任务。"
    >
      <template #actions>
        <el-button @click="checkStatus">检查状态</el-button>
        <!-- 对齐静态版：非运行状态可编辑配置 -->
        <el-button v-if="task && task.status !== 'running'" type="primary" plain @click="openEditConfig">
          编辑配置
        </el-button>
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
      </template>
    </PageToolbar>

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
                <TaskProgressCell :current-step="task.current_step || 0" :total-steps="task.total_steps || 0" />
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
              <el-descriptions-item label="创建时间">{{ task.created_at || '-' }}</el-descriptions-item>
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
            <LogViewer :logs="logs" height="500px" />
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
                <!-- 对齐静态版：单任务结果导出 Excel -->
                <el-button size="small" type="success" :loading="exporting" @click="handleExport">
                  导出 Excel
                </el-button>
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
              <el-table-column label="执行结果" min-width="260">
                <template #default="{ row }">
                  <!-- C3 任务：I15-I23 摘要网格（flat_result 优先），其余任务保持 JSON 预览 -->
                  <template v-if="isC3Task && isPlainObject(row.result)">
                    <div v-if="resultSummaryItems(row.result).length" class="result-summary-grid">
                      <div
                        v-for="item in resultSummaryItems(row.result)"
                        :key="item.key"
                        class="result-summary-item"
                      >
                        <div class="result-summary-label">{{ item.label }}</div>
                        <div class="result-summary-value">{{ item.value }}</div>
                      </div>
                    </div>
                    <span v-else>{{ formatResultPreview(row.result) }}</span>
                  </template>
                  <span v-else>{{ formatResultPreview(row.result) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="timestamp" label="时间" width="160" show-overflow-tooltip />
              <el-table-column label="耗时" width="100">
                <template #default="{ row }">{{ durationMap.get(row) || '-' }}</template>
              </el-table-column>
              <el-table-column label="操作" width="80">
                <template #default="{ row }">
                  <el-button link type="primary" @click="viewResult(row)">更多</el-button>
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
                    <el-descriptions-item label="Token 名称">
                      {{ taskConfigSummary.tokenName }}
                    </el-descriptions-item>
                    <el-descriptions-item label="Token 选择模式">
                      {{ taskConfigSummary.tokenSelectionMode }}
                    </el-descriptions-item>
                    <el-descriptions-item label="代理">
                      {{ taskConfigSummary.proxy }}
                    </el-descriptions-item>
                    <el-descriptions-item label="结束日期">
                      {{ taskConfigSummary.endDate }}
                    </el-descriptions-item>
                    <el-descriptions-item label="K线数据源">
                      {{ taskConfigSummary.klineDataSource }}
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
              <CodeBlock :content="task.config || {}" />
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </div>

    <el-drawer v-model="resultDrawerVisible" :title="resultDrawerTitle" :size="isMobile ? '100%' : '560px'">
      <div v-if="currentResult" class="task-detail-page__drawer-body">
        <div class="task-detail-page__drawer-section">
          <div class="task-detail-page__chart-title">参数信息</div>
          <!-- C3 任务：参数以徽标展示（K线输入列渲染为“K线范围”摘要），其余保持 JSON -->
          <template v-if="isC3Task">
            <div class="task-detail-page__param-badges">
              <el-tag
                v-for="(value, idx) in parameterValues(currentResult.parameters)"
                :key="idx"
                type="info"
                size="small"
              >
                {{ formatParameterValue(value) }}
              </el-tag>
              <span v-if="!parameterValues(currentResult.parameters).length" class="panel-note">-</span>
            </div>
          </template>
          <CodeBlock v-else :content="currentResult.parameters" />
        </div>
        <div class="task-detail-page__drawer-section">
          <div class="task-detail-page__chart-title">执行结果</div>
          <!-- C3 任务：指标明细表 + 模型/指数收益分析卡 -->
          <template v-if="isC3Task && isPlainObject(currentResult.result)">
            <div class="panel-note">{{ resultDrawerMeta }}</div>
            <el-row
              v-if="currentResultStartReturn || currentResultIndexReturn"
              :gutter="12"
              class="task-detail-page__return-row"
            >
              <el-col v-if="currentResultStartReturn" :span="12">
                <div class="sub-card task-detail-page__return-card">
                  <div class="task-detail-page__chart-title">模型收益分析</div>
                  <div
                    v-for="line in returnCardLines(currentResultStartReturn)"
                    :key="line.label"
                    class="task-detail-page__return-line"
                  >
                    <span class="task-detail-page__return-label">{{ line.label }}</span>
                    <span>{{ line.value }}</span>
                  </div>
                </div>
              </el-col>
              <el-col v-if="currentResultIndexReturn" :span="12">
                <div class="sub-card task-detail-page__return-card">
                  <div class="task-detail-page__chart-title">指数收益分析</div>
                  <div
                    v-for="line in returnCardLines(currentResultIndexReturn)"
                    :key="line.label"
                    class="task-detail-page__return-line"
                  >
                    <span class="task-detail-page__return-label">{{ line.label }}</span>
                    <span>{{ line.value }}</span>
                  </div>
                </div>
              </el-col>
            </el-row>
            <el-table
              v-if="currentResultMetricRows.length"
              :data="currentResultMetricRows"
              size="small"
              border
              class="task-detail-page__metric-table"
            >
              <el-table-column prop="label" label="指标" width="200" />
              <el-table-column label="值">
                <template #default="{ row }">
                  <pre
                    v-if="row.isObject"
                    class="task-detail-page__metric-pre"
                  >{{ JSON.stringify(row.value, null, 2) }}</pre>
                  <span v-else>{{ metricDisplayText(row.value) }}</span>
                </template>
              </el-table-column>
            </el-table>
            <div v-else class="panel-note">无详细指标</div>
          </template>
          <CodeBlock v-else :content="currentResult.result" />
        </div>
        <div v-if="currentResult.error_message" class="task-detail-page__drawer-section">
          <div class="task-detail-page__chart-title">错误信息</div>
          <CodeBlock :content="currentResult.error_message" variant="danger" />
        </div>
      </div>
    </el-drawer>

    <!-- 编辑配置弹窗（对齐静态版 editConfigModal，仅非运行状态可编辑） -->
    <el-dialog v-model="editConfigVisible" title="编辑任务配置" width="720px" :fullscreen="isMobile">
      <el-alert
        type="warning"
        :closable="false"
        title="注意：修改配置后，建议从头重新执行任务以确保数据一致性。如果从断点继续，请确保参数组合数量和顺序没有改变。"
        class="task-detail-page__edit-alert"
      />
      <el-form label-width="110px">
        <el-form-item label="任务名称">
          <el-input v-model="editForm.name" placeholder="请输入任务名称" />
        </el-form-item>
        <el-form-item label="任务描述">
          <el-input v-model="editForm.description" type="textarea" :rows="2" placeholder="请输入任务描述" />
        </el-form-item>
        <el-divider content-position="left">Google Sheet 配置</el-divider>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="电子表格ID">
              <el-input v-model="editForm.spreadsheet_id" placeholder="请输入电子表格ID" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="工作表名称">
              <el-input v-model="editForm.sheet_name" placeholder="请输入工作表名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Sheet Title">
              <el-input v-model="editForm.title" placeholder="请输入 Google Sheet 标题" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Token文件路径">
              <el-input v-model="editForm.token_file" placeholder="data/token.json" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="代理URL">
              <el-input v-model="editForm.proxy_url" placeholder="http://proxy.example.com:8080" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-divider content-position="left">参数配置</el-divider>
        <div
          v-for="(_, idx) in editForm.parameterGroups"
          :key="idx"
          class="control-row control-row--stretch task-detail-page__edit-param"
        >
          <el-input
            v-model="editForm.parameterGroups[idx]"
            :placeholder="`参数组 ${idx + 1}，用逗号分隔，例如: 1, 2, 3`"
          />
          <el-button
            type="danger"
            plain
            :disabled="editForm.parameterGroups.length <= 1"
            @click="editForm.parameterGroups.splice(idx, 1)"
          >
            删除
          </el-button>
        </div>
        <el-button size="small" @click="editForm.parameterGroups.push('')">添加参数组</el-button>
        <el-divider content-position="left">单元格位置配置</el-divider>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="参数位置">
              <el-input v-model="editForm.parameter_positions" placeholder='["B6","B7","B9"]' />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="检查位置">
              <el-input v-model="editForm.check_positions" placeholder='["I6","I7","I9"]' />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="结果位置">
              <el-input v-model="editForm.result_positions" placeholder='["I15","I16"]' />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="editConfigVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingConfig" @click="saveTaskConfig">保存配置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import {
  getTask,
  getTaskLogs,
  getTaskResults,
  cancelTask,
  restartTask,
  updateTaskConfig,
  exportTaskResults,
  checkTaskStatus as apiCheckStatus
} from '@/api/task'
import { getConfig } from '@/api/config'
import StatusTag from '@/components/StatusTag.vue'
import PageToolbar from '@/components/PageToolbar.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'
import LogViewer from '@/components/LogViewer.vue'
import CodeBlock from '@/components/CodeBlock.vue'
import { formatDateTime } from '@/utils/format'
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

// 刷新间隔：读配置 detail_refresh_interval，读不到用静态版默认 60000（仅 running/pending 轮询）
const refreshInterval = ref(60000)

// 导出 Excel
const exporting = ref(false)

// 编辑配置弹窗
const editConfigVisible = ref(false)
const savingConfig = ref(false)
const editForm = reactive({
  name: '',
  description: '',
  spreadsheet_id: '',
  sheet_name: '',
  title: '',
  token_file: '',
  proxy_url: '',
  parameterGroups: [''],
  parameter_positions: '[]',
  check_positions: '[]',
  result_positions: '[]'
})

const isC3Task = computed(() => String(task.value?.task_type || '').toLowerCase() === 'google_sheet')

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
    // 配置摘要补 Token 名称 / Token 选择模式 / 结束日期 / K线数据源（对齐静态版 loadTaskConfig）
    tokenName: config.token_name || '-',
    tokenSelectionMode:
      config.token_selection_mode === '__random__'
        ? '随机 Token'
        : config.token_selection_mode || '-',
    proxy: config.proxy_url || '-',
    endDate: config.end_date || '-',
    klineDataSource: config.kline_data_source || config.data_source || '-',
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
    allResults.value = res.items || []
    const total = res.total || 0
    const successCount = allResults.value.filter((item) => item.success).length
    resultSummary.value = {
      success_count: successCount,
      failed_count: Math.max(total - successCount, 0),
      success_rate: total ? Math.round((successCount / total) * 1000) / 10 : 0,
    }
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

// ── 耗时列：结果 timestamp 与上一条 / 任务开始时间的差值（对齐静态版 renderResults 的耗时计算）──

// 对齐静态版 formatDuration：<60 秒、<60 分钟、小时三档
function formatDuration(seconds) {
  if (seconds < 60) {
    return `${seconds}秒`
  } else if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}分${remainingSeconds}秒`
  }
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return `${hours}小时${minutes}分钟`
}

const durationMap = computed(() => {
  const map = new Map()
  let previousTime = task.value?.start_time ? new Date(task.value.start_time) : null
  if (previousTime && Number.isNaN(previousTime.getTime())) previousTime = null
  for (const item of allResults.value) {
    const current = item?.timestamp ? new Date(item.timestamp) : null
    const valid = current && !Number.isNaN(current.getTime())
    let text = '-'
    if (valid && previousTime) {
      const seconds = Math.round((current.getTime() - previousTime.getTime()) / 1000)
      if (seconds >= 0) text = formatDuration(seconds)
    }
    map.set(item, text)
    if (valid) previousTime = current
  }
  return map
})

// ── C3 结构化结果展示（对齐静态版 google_sheet_detail.js，映射表逐值抄录）──

function isPlainObject(value) {
  return value != null && typeof value === 'object' && !Array.isArray(value)
}

function getFlatResult(metrics) {
  if (!isPlainObject(metrics)) {
    return null
  }
  return isPlainObject(metrics.flat_result) ? metrics.flat_result : null
}

function getPreferredMetricValue(metrics, key) {
  const flatResult = getFlatResult(metrics)
  if (flatResult && flatResult[key] != null) {
    return flatResult[key]
  }
  return metrics && metrics[key] != null ? metrics[key] : null
}

function getFirstMetricValue(source, keys) {
  if (!isPlainObject(source)) {
    return null
  }
  for (const key of keys) {
    if (source[key] != null) {
      return source[key]
    }
  }
  return null
}

function getModelSharpeValue(metrics, type) {
  const flatResult = getFlatResult(metrics)

  if (flatResult) {
    if (type === 'index') {
      return getFirstMetricValue(flatResult, ['index_sharpe_ratio', 'index_sharp', 'ixpl', 'i_xpl', 'index_xpl'])
    }
    return getFirstMetricValue(flatResult, ['start_sharpe_ratio', 'start_sharp', 'sxpl', 's_xpl', 'start_xpl'])
  }

  const legacyPerformanceAnalysis = type === 'index'
    ? (metrics.index_return_xpl || {})
    : (metrics.start_return_xpl || {})
  return legacyPerformanceAnalysis.sharpe_ratio != null ? legacyPerformanceAnalysis.sharpe_ratio : null
}

function shouldShowDetailMetric(key) {
  return !['start_return_xpl', 'index_return_xpl', 'analyze_result'].includes(String(key))
}

function formatMetricRawValue(value, digits) {
  if (value == null || value === '') {
    return null
  }
  const numericValue = Number(value)
  if (Number.isFinite(numericValue)) {
    return typeof digits === 'number' ? numericValue.toFixed(digits) : String(numericValue)
  }
  return value
}

function formatMetricText(value, digits) {
  const formatted = formatMetricRawValue(value, digits)
  if (formatted == null) {
    return '-'
  }
  return String(formatted)
}

// 抽屉“值”列展示文本：数值格式化，对象/数组由模板渲染 JSON
function metricDisplayText(value) {
  if (isPlainObject(value) || Array.isArray(value)) return ''
  return formatMetricText(value, 6)
}

// 中文映射表（static/js/pages/google_sheet_detail.js c3MetricDisplayNameMap 原样抄录）
const c3MetricDisplayNameMap = {
  B6: 'X Multiplier',
  B7: '单边保护',
  B8: '单边保护',
  B9: '中立限仓',
  B10: '指数跟踪',
  B11: '一窝蜂 smoothing',
  B12: '一窝蜂 bordering',
  I15: 'Return%',
  I16: 'Annualized',
  I17: 'Max DD%',
  I18: 'Index Return',
  I19: 'Annualized',
  I20: 'Index max dd',
  I21: 'Fee total',
  I22: 'Fee annualized',
  I23: '年换手率',
  annualized_return_diff: '年化超额收益',
  avg_monthly_excess_returns: '平均月超额',
  excess_drawdown_winning_rate: '超额回撤胜率',
  excess_maximum_number_of_backtest_repair_days: '超额最大修复天数',
  excess_sortino: '超额索提诺',
  excess_sharpe: '超额夏普',
  index_annual_std_dev: '指数年化波动率',
  index_annualized_return: '指数年化收益',
  index_avg_monthly_return: '指数平均月收益率',
  index_avg_monthly_return_common: '指数平均月收益率',
  index_kama_ratio: '指数卡玛比率',
  index_monthly_return_volatility: '指数月收益率波动率',
  index_monthly_std_dev: '指数月度标准差',
  index_profit_annual: '指数盈利年份百分比',
  index_profit_monthly_percentage: '指数月盈利百分比',
  index_sharpe_ratio: '指数夏普比率',
  index_sortino_ratio: '指数索提诺比率',
  max_drawdown: '年最大超额回撤',
  monthly_excess_return_percentage_last_return: '月超额收益胜率',
  monthly_excess_volatility: '月超额波动率',
  outperform_year: '跑赢年份(百分比)',
  start_annual_std_dev: '模型年化波动率',
  start_annualized_return: '模型年化收益',
  start_avg_monthly_return: '模型平均月收益率',
  start_avg_monthly_return_common: '模型平均月收益率',
  start_drawdown: '年最大回撤',
  start_kama_ratio: '模型卡玛比率',
  start_maximum_number_of_backtest_repair_days: '最大修复天数',
  start_monthly_return_volatility: '模型月收益率波动率',
  start_monthly_std_dev: '模型月度标准差',
  start_profit_annual: '模型盈利年份百分比',
  start_profit_monthly_percentage: '模型月盈利百分比',
  start_sharpe_ratio: '模型夏普比率',
  start_sortino_ratio: '模型索提诺比率'
}

// 摘要网格取值口径（I15-I23 + 指数/模型夏普，对齐静态版 c3SummaryMetrics / renderResultSummary）
const c3SummaryMetrics = [
  ['I15', 'Return%'],
  ['I16', 'Annualized'],
  ['I17', 'Max DD%'],
  ['I18', 'Index Return'],
  ['I19', 'Annualized'],
  ['I20', 'Index max dd'],
  ['I21', 'Fee total'],
  ['I22', 'Fee annualized'],
  ['I23', '年换手率'],
  ['index_sharpe_ratio', '指数夏普'],
  ['start_sharpe_ratio', '模型夏普']
]

function metricLabel(key) {
  return c3MetricDisplayNameMap[String(key)] || String(key)
}

function resultSummaryItems(resultData) {
  if (!isPlainObject(resultData)) return []
  const items = []
  for (const [key, label] of c3SummaryMetrics) {
    let value
    if (key === 'index_sharpe_ratio') {
      value = getModelSharpeValue(resultData, 'index')
    } else if (key === 'start_sharpe_ratio') {
      value = getModelSharpeValue(resultData, 'start')
    } else {
      value = getPreferredMetricValue(resultData, key)
    }
    if (value == null) continue
    items.push({ key, label, value: formatMetricText(value, 6) })
  }
  return items
}

function parseMetricKey(key) {
  const m = String(key).match(/^([A-Za-z_]+)(\d+)?$/)
  if (m) {
    return { prefix: m[1], num: m[2] != null ? parseInt(m[2], 10) : null }
  }
  return { prefix: String(key), num: null }
}

function sortMetricKeys(keys) {
  return keys.slice().sort((a, b) => {
    const ia = String(a).match(/^I(\d+)$/i)
    const ib = String(b).match(/^I(\d+)$/i)
    if (ia && ib) return parseInt(ia[1], 10) - parseInt(ib[1], 10)
    if (ia && !ib) return -1
    if (!ia && ib) return 1

    const pa = parseMetricKey(a)
    const pb = parseMetricKey(b)
    if (pa.prefix !== pb.prefix) {
      return pa.prefix.localeCompare(pb.prefix)
    }
    if (pa.num !== null && pb.num !== null) {
      return pa.num - pb.num
    }
    return String(a).localeCompare(String(b))
  })
}

// ── 结果抽屉（C3 结构化渲染）──

const resultDrawerTitle = computed(() =>
  currentResult.value ? `结果详情 #${(currentResult.value.step_index || 0) + 1}` : '结果详情'
)

const resultDrawerMeta = computed(() => {
  const result = currentResult.value
  if (!result) return ''
  return [
    `参数组合：${formatParameterCombinationText(result.parameters) || '-'}`,
    `执行时间：${result.timestamp ? formatDateTime(result.timestamp) : '-'}`,
    `状态：${result.success ? '成功' : '失败'}`
  ].join(' · ')
})

const currentResultMetrics = computed(() =>
  isPlainObject(currentResult.value?.result) ? currentResult.value.result : {}
)

const currentResultHasFlatResult = computed(() => !!getFlatResult(currentResultMetrics.value))

const currentResultStartReturn = computed(() =>
  currentResultHasFlatResult.value ? null : (currentResultMetrics.value.start_return_xpl || null)
)

const currentResultIndexReturn = computed(() =>
  currentResultHasFlatResult.value ? null : (currentResultMetrics.value.index_return_xpl || null)
)

const currentResultMetricRows = computed(() => {
  const metrics = currentResultMetrics.value
  if (!isPlainObject(metrics)) return []
  const baseKeys = ['I15', 'I16', 'I17', 'I18', 'I19', 'I20', 'I21', 'I22', 'I23']
    .filter((key) => metrics[key] != null)
  const detailKeys = sortMetricKeys(Object.keys(metrics).filter(shouldShowDetailMetric))
  return Array.from(new Set([...baseKeys, ...detailKeys])).map((key) => ({
    key,
    label: metricLabel(key),
    value: metrics[key],
    isObject: isPlainObject(metrics[key]) || Array.isArray(metrics[key])
  }))
})

// 收益分析卡行（对齐静态版 renderStatLine 字段）
function returnCardLines(source) {
  if (!isPlainObject(source)) return []
  return [
    { label: '起始日期', value: source.start_date ?? '-' },
    { label: '结束日期', value: source.end_date ?? '-' },
    { label: '月份数', value: source.month_count ?? '-' },
    { label: '平均月收益', value: formatMetricText(source.avg_monthly_return, 6) },
    { label: '月度波动率', value: formatMetricText(source.monthly_std_dev, 6) },
    { label: '年化波动率', value: formatMetricText(source.annual_std_dev, 6) },
    { label: '夏普率', value: formatMetricText(source.sharpe_ratio, 6) }
  ]
}

// ── 参数徽标 / K线范围（对齐静态版 formatParameterValue）──

function isKlinePoint(value) {
  return isPlainObject(value) && (value.stock_date !== undefined || value.stock_val !== undefined)
}

function formatKlinePoint(value) {
  const date = value && value.stock_date != null ? String(value.stock_date) : '-'
  const stockVal = value && value.stock_val != null ? String(value.stock_val) : ''
  return stockVal ? `${date}(${stockVal})` : date
}

function formatParameterValue(value) {
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  if (Array.isArray(value)) {
    if (value.length && value.every(isKlinePoint)) {
      const first = value[0]
      const last = value[value.length - 1]
      return `K线范围：${formatKlinePoint(first)} ~ ${formatKlinePoint(last)}`
    }
    return value.map(formatParameterValue).join(', ')
  }
  if (isPlainObject(value)) {
    if (isKlinePoint(value)) {
      return formatKlinePoint(value)
    }
    return JSON.stringify(value)
  }
  return String(value)
}

function getParameterValues(parameters) {
  if (Array.isArray(parameters)) return parameters
  if (parameters === null || parameters === undefined || parameters === '') return []
  return [parameters]
}

function formatParameterCombinationText(parameters) {
  const values = getParameterValues(parameters).map(formatParameterValue).filter(Boolean)
  return values.length ? values.join(', ') : '-'
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
    const sc = res?.status_check
    if (!sc) {
      ElMessage.error('检查任务状态失败: 未知错误')
      return
    }
    // 展示全量 status_check（对齐静态版 checkTaskStatus）
    let message = `数据库状态: ${sc.db_status || '未知'}\n`
    message += `内存运行状态: ${sc.memory_running ? '运行中' : '未运行'}\n`
    message += `当前步骤: ${sc.current_step ?? 0}/${sc.total_steps ?? 0}`
    if (sc.latest_log_time) {
      message += `\n最新日志时间: ${formatDateTime(sc.latest_log_time)}`
    }
    if (sc.can_restart) {
      message += `\n\n检测到问题: ${sc.restart_reason || '-'}\n建议从断点重启任务，是否立即重启？`
      try {
        await ElMessageBox.confirm(message, '状态检查结果', {
          type: 'warning',
          confirmButtonText: '从断点重启',
          cancelButtonText: '取消'
        })
      } catch {
        return
      }
      try {
        await restartTask(taskId, { resume_from_checkpoint: true })
        ElMessage.success('任务已从断点重启')
        loadAll()
      } catch (e) {
        ElMessage.error(`重启失败: ${e?.message || '未知错误'}`)
      }
      return
    }
    message += `\n\n${sc.restart_reason || '任务状态正常'}`
    ElMessageBox.alert(message, '状态检查结果', { type: 'info' }).catch(() => {})
  } catch (e) {
    ElMessage.error(`检查任务状态失败: ${e?.message || '未知错误'}`)
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
    // 对齐静态版 goToCreateRestartTask：跳转到创建页并透传 restart_task_id（分发器再解析版本）
    const version = route.query.version
    router.push({
      path: '/task/create',
      query: { restart_task_id: taskId, ...(version ? { version } : {}) }
    })
    return
  }
  try {
    await restartTask(taskId, { resume_from_checkpoint: cmd === 'resume' })
    ElMessage.success(cmd === 'resume' ? '任务已从断点重启' : '任务已从头重启')
    loadAll()
  } catch (e) {
    ElMessage.error(`${cmd === 'resume' ? '断点重启' : '从头重启'}失败: ${e?.message || '未知错误'}`)
  }
}

// ── 导出 Excel（对齐静态版 exportResultsToCSV：blob 下载，文件名优先取 Content-Disposition）──

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

async function handleExport() {
  if (!taskId) {
    ElMessage.error('任务ID为空，无法导出')
    return
  }
  exporting.value = true
  try {
    const { blob, filename } = await exportTaskResults(taskId)
    downloadBlob(blob, filename || `task_results_${taskId}.xlsx`)
    ElMessage.success('Excel 导出已开始下载')
  } catch (e) {
    ElMessage.error(`导出失败: ${e?.message || '未知错误'}`)
  } finally {
    exporting.value = false
  }
}

// ── 编辑配置（对齐静态版 openEditConfigModal / saveTaskConfig）──

function openEditConfig() {
  if (!task.value) {
    ElMessage.error('任务数据未加载')
    return
  }
  const config = task.value.config || {}

  editForm.name = task.value.name || ''
  editForm.description = task.value.description || ''
  editForm.spreadsheet_id = config.spreadsheet_id || ''
  editForm.sheet_name = config.sheet_name || ''
  editForm.title = config.title || config.spreadsheet_title || ''
  editForm.token_file = config.token_file || 'data/token.json'
  editForm.proxy_url = config.proxy_url || ''
  editForm.parameter_positions = JSON.stringify(config.parameter_positions || [])
  editForm.check_positions = JSON.stringify(config.check_positions || [])
  editForm.result_positions = JSON.stringify(config.result_positions || [])

  // 参数组编辑器：逗号分隔文本，无参数时保留一个空组
  const parameters = Array.isArray(config.parameters) ? config.parameters : []
  editForm.parameterGroups = parameters.length
    ? parameters.map((group) => (Array.isArray(group) ? group.join(', ') : ''))
    : ['']

  editConfigVisible.value = true
}

async function saveTaskConfig() {
  const name = editForm.name.trim()
  if (!name) {
    ElMessage.error('请输入任务名称')
    return
  }
  const spreadsheetId = editForm.spreadsheet_id.trim()
  if (!spreadsheetId) {
    ElMessage.error('请输入电子表格ID')
    return
  }

  // 参数组：逗号分隔 → 数组（数字优先，对齐静态版参数解析）
  const parameters = []
  for (const groupText of editForm.parameterGroups) {
    const valuesStr = String(groupText || '').trim()
    if (valuesStr) {
      const values = valuesStr.split(',').map((v) => {
        const trimmed = v.trim()
        const num = parseFloat(trimmed)
        return Number.isNaN(num) ? trimmed : num
      })
      parameters.push(values)
    }
  }
  if (parameters.length === 0) {
    ElMessage.error('请至少添加一组参数')
    return
  }

  let parameterPositions, checkPositions, resultPositions
  try {
    parameterPositions = JSON.parse(editForm.parameter_positions || '[]')
    checkPositions = JSON.parse(editForm.check_positions || '[]')
    resultPositions = JSON.parse(editForm.result_positions || '[]')
  } catch {
    ElMessage.error('位置配置格式错误，请使用JSON数组格式')
    return
  }

  const config = {
    spreadsheet_id: spreadsheetId,
    sheet_name: editForm.sheet_name.trim(),
    title: editForm.title.trim() || null,
    token_file: editForm.token_file.trim(),
    proxy_url: editForm.proxy_url.trim(),
    parameters,
    parameter_positions: parameterPositions,
    check_positions: checkPositions,
    result_positions: resultPositions
  }

  savingConfig.value = true
  try {
    await updateTaskConfig(taskId, { name, description: editForm.description.trim(), config })
    ElMessage.success('配置更新成功')
    editConfigVisible.value = false
    loadAll()
  } catch (e) {
    ElMessage.error(`配置更新失败: ${e?.message || '未知错误'}`)
  } finally {
    savingConfig.value = false
  }
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

const { stop: stopPolling, tick: pollerTick } = usePolling(
  async () => {
    await loadTask()
    await loadLogs()

    if (activeTab.value === 'results') {
      await loadResults()
    }
  },
  {
    interval: refreshInterval.value,
    immediate: false,
    isActive: () => task.value?.status === 'running' || task.value?.status === 'pending',
  }
)

// usePolling 的间隔在启动时固定，读取配置后若不同则停用内置定时器、按配置间隔自建
let customPollTimer = null

onMounted(async () => {
  // 刷新间隔读配置（detail_refresh_interval，默认 60000），失败沿用默认
  try {
    const res = await getConfig()
    const interval = Number(res?.config?.detail_refresh_interval)
    if (Number.isFinite(interval) && interval > 0 && interval !== refreshInterval.value) {
      refreshInterval.value = interval
      stopPolling()
      customPollTimer = window.setInterval(() => pollerTick(), interval)
    }
  } catch {}
  void loadAll()
})

onUnmounted(() => {
  if (customPollTimer) {
    window.clearInterval(customPollTimer)
    customPollTimer = null
  }
})

onUnmounted(() => {
  if (resultChart) resultChart.destroy()
})
</script>

<style scoped>
/* C3 结果摘要网格（对齐静态版 result-summary-grid） */
.result-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 6px;
}

.result-summary-item {
  padding: 4px 8px;
  border: 1px solid var(--app-border);
  border-radius: 6px;
  background: var(--app-surface);
}

.result-summary-label {
  font-size: 11px;
  color: var(--app-text-muted);
}

.result-summary-value {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text);
  word-break: break-all;
}

.task-detail-page__param-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.task-detail-page__return-row {
  margin-bottom: 8px;
}

.task-detail-page__return-card {
  height: 100%;
}

.task-detail-page__return-line {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  padding: 2px 0;
  border-bottom: 1px dashed var(--app-border);
}

.task-detail-page__return-label {
  color: var(--app-text-muted);
}

.task-detail-page__metric-table {
  margin-top: 8px;
}

.task-detail-page__metric-pre {
  margin: 0;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}

.task-detail-page__edit-alert {
  margin-bottom: 12px;
}

.task-detail-page__edit-param {
  margin-bottom: 8px;
}

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
