<template>
  <div class="app-page task-detail-page">
    <PageToolbar
      eyebrow="Task Monitor"
      title="任务详情"
      description="查看任务状态、执行日志、结果趋势和当前配置，支持停止与重启任务。"
    >
      <template #actions>
        <!-- 对齐静态版：手动刷新 + 刷新频率下拉（5s/15s/30s/60s/关闭） -->
        <el-select v-model="refreshInterval" class="refresh-frequency-select">
          <el-option
            v-for="option in refreshFrequencyOptions"
            :key="option.value"
            :value="option.value"
            :label="option.label"
          />
        </el-select>
        <el-button :loading="manualRefreshing" @click="handleManualRefresh">手动刷新</el-button>
        <el-button @click="checkStatus">检查状态</el-button>
        <!-- 对齐静态版：非运行状态可编辑配置 -->
        <el-button v-if="task && task.status !== 'running'" type="primary" plain @click="openEditConfig">
          编辑配置
        </el-button>
        <el-button v-if="task?.status === 'running'" type="warning" @click="handleCancel">停止任务</el-button>
        <!-- 对齐静态版重启枚举：pending/completed/error/cancelled -->
        <el-dropdown v-if="canRestart" @command="handleRestart">
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
              <!-- 对齐静态版：created_at→(end_time||now) 的中文时长 -->
              <el-descriptions-item label="执行时长">{{ executionDurationText }}</el-descriptions-item>
              <el-descriptions-item v-if="task.error_message" label="错误信息">
                <span class="task-detail-page__error-text">{{ task.error_message }}</span>
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>

        <el-col :xs="24" :md="8" class="task-detail-page__metric-col">
          <el-card shadow="never" class="page-section task-detail-page__metric-card">
            <div class="section-heading">
              <h3 class="section-title section-title--muted">执行汇总</h3>
            </div>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-statistic title="成功" :value="resultSummary.success_count ?? 0" />
              </el-col>
              <el-col :span="12">
                <el-statistic title="失败" :value="resultSummary.failed_count ?? 0" />
              </el-col>
            </el-row>
            <el-progress
              :percentage="resultSummary.success_rate ?? 0"
              class="task-detail-page__summary-progress"
            />
          </el-card>
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
                <!-- C4/C5/C7：对齐静态版 results-summary 文案；C3：总条数 -->
                <span class="panel-note">{{ resultsSummaryText }}</span>
              </div>
              <div class="section-actions">
                <el-button size="small" @click="refreshResults">刷新结果</el-button>
                <!-- 对齐静态版：单任务结果导出 Excel -->
                <el-button size="small" type="success" :loading="exporting" @click="handleExport">
                  导出 Excel
                </el-button>
                <!-- 对齐静态版 C7：按股票代码 ZIP 导出 -->
                <el-button
                  v-if="versionKind === 'c7'"
                  size="small"
                  type="success"
                  :loading="exportingStocks"
                  @click="handleExportStocks"
                >
                  按股票代码导出
                </el-button>
              </div>
            </div>

            <div class="sub-card task-detail-page__chart-card">
              <div class="task-detail-page__chart-title">结果趋势</div>
              <div class="task-detail-page__chart-wrap">
                <canvas ref="resultChartRef"></canvas>
              </div>
            </div>

            <!-- C4/C5/C7：按参数组合分组的模型结果卡片（版本化渲染） -->
            <ResultGroupsCards
              v-if="isVersionTask"
              :version="versionKind"
              :results="filteredResults"
              :task-config="parsedTaskConfig"
            />

            <template v-else>
              <el-table :data="filteredResults" stripe class="task-detail-page__table">
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
                    <!-- C3 任务：I15-I23 摘要（flat_result 优先）；无摘要/其他任务展示完整 JSON -->
                    <template v-if="isC3Task && isPlainObject(row.result)">
                      <el-descriptions
                        v-if="resultSummaryItems(row.result).length"
                        :column="4"
                        size="small"
                      >
                        <el-descriptions-item
                          v-for="item in resultSummaryItems(row.result)"
                          :key="item.key"
                          :label="item.label"
                        >
                          {{ item.value }}
                        </el-descriptions-item>
                      </el-descriptions>
                      <CodeBlock v-else :content="row.result" />
                    </template>
                    <span v-else-if="row.result == null">-</span>
                    <CodeBlock v-else :content="row.result" />
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
            </template>

            <div class="task-detail-page__pagination">
              <el-pagination
                v-model:current-page="resultPage"
                v-model:page-size="resultPageSize"
                :total="resultsTotal"
                :page-sizes="[10, 20, 50, 100]"
                layout="total, sizes, prev, pager, next"
                @current-change="handleResultPageChange"
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
                    <!-- C4/C5/C7 版本字段（对齐各版本 loadTaskConfig 的 configItems） -->
                    <template v-if="isVersionTask">
                      <el-descriptions-item label="统计方式">
                        {{ versionConfigSummary.countMode }}
                      </el-descriptions-item>
                      <el-descriptions-item v-if="versionKind !== 'c4'" label="价格类型">
                        {{ versionConfigSummary.priceMode }}
                      </el-descriptions-item>
                      <el-descriptions-item label="市场类型">
                        {{ versionConfigSummary.marketType }}
                      </el-descriptions-item>
                      <el-descriptions-item label="市场代码">
                        {{ versionConfigSummary.marketCode }}
                      </el-descriptions-item>
                      <el-descriptions-item label="时间范围类型">
                        {{ versionConfigSummary.dateRangeMode }}
                      </el-descriptions-item>
                      <el-descriptions-item label="数据时间范围">
                        {{ versionConfigSummary.dateRange }}
                      </el-descriptions-item>
                      <el-descriptions-item v-if="versionKind !== 'c4'" label="移除的近年区间">
                        {{ versionConfigSummary.excludedYears }}
                      </el-descriptions-item>
                      <el-descriptions-item label="认证方式">
                        {{ versionConfigSummary.tokenType }}
                      </el-descriptions-item>
                      <el-descriptions-item label="Token 路径">
                        {{ versionConfigSummary.tokenFile }}
                      </el-descriptions-item>
                    </template>
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
                  <!-- C4/C5/C7：工作表配置逐表列出（对齐静态版 sheetsBlock） -->
                  <template v-if="isVersionTask">
                    <div class="task-detail-page__chart-title task-detail-page__sheets-title">工作表配置</div>
                    <el-table v-if="versionSheets.length" :data="versionSheets" size="small" border>
                      <el-table-column type="index" label="表" width="60" />
                      <el-table-column prop="spreadsheet_id" label="表格 ID" min-width="160" show-overflow-tooltip>
                        <template #default="{ row }">{{ row.spreadsheet_id || '-' }}</template>
                      </el-table-column>
                      <el-table-column prop="sheet_name" label="工作表" min-width="120" show-overflow-tooltip>
                        <template #default="{ row }">{{ row.sheet_name || '-' }}</template>
                      </el-table-column>
                      <el-table-column label="标题" min-width="120" show-overflow-tooltip>
                        <template #default="{ row }">{{ row.title || '-' }}</template>
                      </el-table-column>
                    </el-table>
                    <div v-else class="panel-note">无工作表配置</div>
                  </template>
                </div>
              </el-col>
            </el-row>

            <div class="sub-card">
              <div class="task-detail-page__chart-title">完整配置</div>
              <CodeBlock :content="parsedTaskConfig" />
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

    <!-- C3 编辑配置弹窗（对齐静态版 google_sheet/detail.html editConfigModal，仅非运行状态可编辑） -->
    <el-dialog
      v-if="!isVersionTask"
      v-model="editConfigVisible"
      title="编辑任务配置"
      width="720px"
      :fullscreen="isMobile"
    >
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

    <!-- C4/C5/C7 版本化编辑配置弹窗（对齐 static/js/common/business/config-edit.js） -->
    <ConfigEditDialog
      v-if="isVersionTask"
      v-model:visible="versionEditVisible"
      :task="task"
      :version="versionKind"
      @saved="loadAll"
    />
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
  exportTaskResultsByStocks,
  checkTaskStatus as apiCheckStatus
} from '@/api/task'
import { getConfig } from '@/api/config'
import StatusTag from '@/components/StatusTag.vue'
import PageToolbar from '@/components/PageToolbar.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'
import LogViewer from '@/components/LogViewer.vue'
import CodeBlock from '@/components/CodeBlock.vue'
import ConfigEditDialog from '@/components/ConfigEditDialog.vue'
import ResultGroupsCards from './components/ResultGroupsCards.vue'
import {
  formatCountMode,
  formatDateRangeMode,
  formatExcludedYears,
  formatExecutionDuration,
  formatMarketType,
  formatPriceMode,
  formatTokenType
} from './components/versionShared'
import { formatDateTime } from '@/utils/format'
import { useChartJs } from '@/composables/useChartJs'
import { useResponsive } from '@/composables/useResponsive'

const route = useRoute()
const router = useRouter()
const { isMobile } = useResponsive()
const taskId = route.params.id
const task = ref(null)
const logs = ref([])
const allResults = ref([]) // 当前页的结果数据（服务端分页）
const resultsTotal = ref(0)
const resultStats = ref({ totalSuccess: null, totalFailed: null })
const loading = ref(false)
const activeTab = ref('logs')
const logContainerRef = ref()
const resultPage = ref(1)
const resultPageSize = ref(20)
const pageSizeInitialized = ref(false)
const resultFilter = ref('all')
const resultDrawerVisible = ref(false)
const currentResult = ref(null)
const resultChartRef = ref(null)
let resultChart = null
const { loadChartJs } = useChartJs()

// ── 刷新控制（对齐静态版 manual-refresh-btn / refresh-frequency：5s/15s/30s/60s/关闭）──

const refreshFrequencyOptions = [
  { value: 5000, label: '5秒' },
  { value: 15000, label: '15秒' },
  { value: 30000, label: '30秒' },
  { value: 60000, label: '60秒' },
  { value: 0, label: '关闭' }
]
// 默认 60000，onMounted 时读配置 detail_refresh_interval 覆盖
const refreshInterval = ref(60000)
const manualRefreshing = ref(false)

// ── 任务类型（C3 / C4 / C5 / C7 分发）──

const taskTypeNormalized = computed(() => String(task.value?.task_type || '').toLowerCase())
const isC3Task = computed(() => taskTypeNormalized.value === 'google_sheet')
const versionKind = computed(() => {
  if (taskTypeNormalized.value === 'google_sheet_c4') return 'c4'
  if (taskTypeNormalized.value === 'google_sheet_c5') return 'c5'
  if (taskTypeNormalized.value === 'google_sheet_c7') return 'c7'
  return null
})
const isVersionTask = computed(() => !!versionKind.value)

// 重启下拉显示条件（对齐静态版状态枚举：pending/completed/error/cancelled）
const canRestart = computed(() =>
  ['pending', 'completed', 'error', 'cancelled'].includes(task.value?.status)
)

// 任务配置统一解析（config 可能是 JSON 字符串，对齐静态版 loadTaskDetail 的兼容处理）
const parsedTaskConfig = computed(() => {
  const raw = task.value?.config
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw)
    } catch {
      return {}
    }
  }
  return raw || {}
})

// C4/C5/C7 工作表配置逐表列出
const versionSheets = computed(() => {
  const sheets = parsedTaskConfig.value.sheets
  return Array.isArray(sheets) ? sheets : []
})

// 执行时长：created_at→(end_time||now)，运行中任务随轮询刷新
const executionDurationText = computed(() => {
  const t = task.value
  if (!t?.created_at) return '-'
  const created = new Date(t.created_at)
  if (Number.isNaN(created.getTime())) return '-'
  const end = t.end_time ? new Date(t.end_time) : new Date()
  const seconds = Math.max(0, Math.round((end.getTime() - created.getTime()) / 1000))
  return formatExecutionDuration(seconds)
})

// ── 导出 Excel / C7 按股票代码 ZIP 导出 ──

const exporting = ref(false)
const exportingStocks = ref(false)

// ── 编辑配置弹窗状态 ──

const editConfigVisible = ref(false)
const versionEditVisible = ref(false)
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

// ── 服务端分页结果 ──

const filteredResults = computed(() => {
  // 对齐静态版：筛选作用于当前页数据（后端暂不支持 success 筛选参数）
  if (resultFilter.value === 'success') return allResults.value.filter((item) => item.success)
  if (resultFilter.value === 'failed') return allResults.value.filter((item) => !item.success)
  return allResults.value
})

// 统计口径用后端 total_success/total_failed（对齐静态版 updateResultsStatistics）
const resultSummary = computed(() => {
  const totalSuccess = resultStats.value.totalSuccess
  const totalFailed = resultStats.value.totalFailed
  let successCount
  let failedCount
  let totalCount
  if (typeof totalSuccess === 'number' && typeof totalFailed === 'number') {
    successCount = totalSuccess
    failedCount = totalFailed
    totalCount = resultsTotal.value || (totalSuccess + totalFailed)
  } else {
    successCount = allResults.value.filter((item) => item.success).length
    totalCount = resultsTotal.value || allResults.value.length
    failedCount = Math.max(totalCount - successCount, 0)
  }
  const successRate = totalCount > 0 ? Math.round((successCount / totalCount) * 100) : 0
  return {
    success_count: successCount,
    failed_count: failedCount,
    success_rate: successRate
  }
})

const resultsSummaryText = computed(() => {
  if (isVersionTask.value) {
    // 对齐静态版 C4/C5/C7 results-summary 文案
    const total = resultsTotal.value
      || (resultSummary.value.success_count + resultSummary.value.failed_count)
    return `共 ${total} 条模型结果，其中成功 ${resultSummary.value.success_count} 条，失败 ${resultSummary.value.failed_count} 条。`
  }
  return `共 ${resultsTotal.value} 条`
})

const taskConfigSummary = computed(() => {
  const config = parsedTaskConfig.value
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

// C4/C5/C7 版本配置摘要（对齐各版本 loadTaskConfig configItems 的取值口径）
const versionConfigSummary = computed(() => {
  const config = parsedTaskConfig.value
  return {
    countMode: formatCountMode(config.count_mode || 'total'),
    priceMode: formatPriceMode(config.price_mode || 'vwap_price'),
    marketType: formatMarketType(config.market_type || 'cn'),
    marketCode: config.exchange_market || config.market || '-',
    dateRangeMode: formatDateRangeMode(config.date_range_mode || 'full'),
    dateRange: `${config.start_date || '-'} ~ ${config.end_date || '-'}`,
    excludedYears: formatExcludedYears(config.exclude_recent_years),
    tokenType: formatTokenType(config.token_type || 'file'),
    tokenFile: config.token_file || '-'
  }
})

async function loadTask() {
  try {
    const res = await getTask(taskId)
    task.value = res.task || res
    // 老版本页（C4/C5/C7）resultsPerPage = 10，C3 = 20：首次加载时按版本设默认页大小
    if (!pageSizeInitialized.value) {
      pageSizeInitialized.value = true
      if (isVersionTask.value) {
        resultPageSize.value = 10
      }
    }
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

// 服务端分页：page & per_page，统计用后端 total_success/total_failed（对齐静态版 loadTaskResults）
async function loadResults(page = resultPage.value) {
  try {
    const res = await getTaskResults(taskId, { page, per_page: resultPageSize.value })
    allResults.value = res.items || []
    resultsTotal.value = res.total || 0
    resultPage.value = res.current_page || page
    resultStats.value = {
      totalSuccess: typeof res.total_success === 'number' ? res.total_success : null,
      totalFailed: typeof res.total_failed === 'number' ? res.total_failed : null
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
    await loadTask()
    await Promise.all([loadLogs(), loadResults()])
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

// ── 结果分页交互（服务端分页）──

function handleResultPageChange(page) {
  loadResults(page)
  scrollResultsToTop()
}

function handleResultPageSizeChange() {
  resultPage.value = 1
  loadResults(1)
}

function refreshResults() {
  loadResults()
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

// ── 导出 Excel / C7 按股票代码 ZIP（blob 下载，文件名优先取 Content-Disposition）──

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

function ensureZipExtension(filename) {
  const safeName = String(filename || 'export.zip').trim() || 'export.zip'
  return safeName.toLowerCase().endsWith('.zip') ? safeName : `${safeName}.zip`
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

// 对齐静态版 exportResultsByStocks：默认名 `${任务名||任务ID}_按股票代码导出.zip`
async function handleExportStocks() {
  if (!taskId) {
    ElMessage.error('任务ID为空，无法导出')
    return
  }
  exportingStocks.value = true
  try {
    const { blob, filename } = await exportTaskResultsByStocks(taskId)
    const defaultName = ensureZipExtension(`${task.value?.name || taskId}_按股票代码导出.zip`)
    downloadBlob(blob, filename || defaultName)
    ElMessage.success('按股票代码导出已开始下载')
  } catch (e) {
    ElMessage.error(`导出失败: ${e?.message || '未知错误'}`)
  } finally {
    exportingStocks.value = false
  }
}

// ── 编辑配置（C3：对齐静态版 openEditConfigModal / saveTaskConfig；C4/C5/C7：ConfigEditDialog）──

function openEditConfig() {
  if (!task.value) {
    ElMessage.error('任务数据未加载')
    return
  }
  if (isVersionTask.value) {
    versionEditVisible.value = true
    return
  }

  const config = parsedTaskConfig.value

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
  // 切换筛选条件时重置到第一页并按服务端分页重取
  resultPage.value = 1
  loadResults(1)
})

watch(activeTab, async (tab) => {
  if (tab === 'results' && allResults.value.length) {
    await nextTick()
    await renderResultChart()
  }
})

// ── 轮询：仅 running/pending 轮询，间隔经下拉可调（0 = 关闭），隐藏页签不重复请求 ──

let refreshTimer = null
let pollingInFlight = false

async function pollTick() {
  if (pollingInFlight || document.hidden) return
  const status = task.value?.status
  if (status && status !== 'running' && status !== 'pending') return
  pollingInFlight = true
  try {
    await loadTask()
    await loadLogs()
    if (activeTab.value === 'results') {
      await loadResults()
    }
  } finally {
    pollingInFlight = false
  }
}

// 手动刷新：全量拉一次任务/日志/结果（对齐静态版 manualRefresh，终态任务也可刷新）
async function handleManualRefresh() {
  if (manualRefreshing.value) return
  manualRefreshing.value = true
  try {
    await loadTask()
    await Promise.all([loadLogs(), loadResults()])
    ElMessage.success('手动刷新完成')
  } catch {
    ElMessage.error('手动刷新失败')
  } finally {
    manualRefreshing.value = false
  }
}

function restartRefreshTimer() {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (refreshInterval.value > 0) {
    refreshTimer = window.setInterval(() => {
      void pollTick()
    }, refreshInterval.value)
  }
}

watch(refreshInterval, () => {
  restartRefreshTimer()
})

onMounted(async () => {
  // 刷新间隔读配置（detail_refresh_interval，默认 60000），失败沿用默认
  try {
    const res = await getConfig()
    const interval = Number(res?.config?.detail_refresh_interval)
    if (Number.isFinite(interval) && interval > 0 && interval !== refreshInterval.value) {
      refreshInterval.value = interval
    }
  } catch {}
  restartRefreshTimer()
  void loadAll()
})

onUnmounted(() => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (resultChart) resultChart.destroy()
})
</script>

<style scoped>
.refresh-frequency-select {
  width: 110px;
}

.task-detail-page__summary-progress {
  margin-top: 16px;
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

.task-detail-page__sheets-title {
  margin-top: 12px;
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

.task-detail-page__drawer-body {
  display: grid;
  gap: 16px;
}

.task-detail-page__drawer-section {
  display: grid;
  gap: 8px;
}
</style>
