<template>
  <div class="app-page admin-tasks-page">
    <PageToolbar eyebrow="管理后台" title="任务管理">
      <template #actions>
        <el-button :size="componentSize" @click="openBatchRestart">批量重启</el-button>
        <el-button type="primary" :size="componentSize" @click="openCreate">创建任务</el-button>
      </template>
    </PageToolbar>

    <FilterToolbar
      :filters="filterConfig"
      v-model="filters"
      @search="doFilter"
      @clear="clearFilters"
    />

    <DataTableCard
      title="任务列表"
      :loading="loading"
      :data="tasks"
      :total="total"
      v-model:page="page"
      v-model:page-size="pageSize"
      :pageSizes="[10, 20, 50, 100]"
      @page-change="loadTasks"
    >
      <el-table-column label="任务" min-width="160">
        <template #default="{ row }">
          <div style="font-weight:600">{{ row.name }}</div>
          <div class="admin-tasks-page__sub-id">{{ row.id?.slice(0,8) }}...</div>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="130">
        <template #default="{ row }"><el-tag size="small" type="info">{{ row.task_type }}</el-tag></template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }"><StatusTag :status="row.status" /></template>
      </el-table-column>
      <el-table-column label="停止确认" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="stopBadgeInfo(row.status).type">{{ stopBadgeInfo(row.status).text }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="参数组" width="70">
        <template #default="{ row }">{{ row.config?.parameters?.length ?? 0 }}</template>
      </el-table-column>
      <el-table-column label="进度" min-width="140">
        <template #default="{ row }">
          <TaskProgressCell :current-step="row.current_step || 0" :total-steps="row.total_steps || 0" />
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ formatDateTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="开始时间" width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ formatDateTime(row.start_time) }}
        </template>
      </el-table-column>
      <el-table-column label="结束时间" width="160" show-overflow-tooltip>
        <template #default="{ row }">
          {{ formatDateTime(row.end_time) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="goTaskDetail(row)">详情</el-button>
          <el-button link type="info" @click="showDetail(row.id)">摘要</el-button>
          <el-button link type="success" @click="openEditTask(row.id)">编辑</el-button>
          <el-button v-if="row.status === 'running'" link type="warning" @click="handleCancel(row.id)">停止</el-button>
          <el-button link type="danger" @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </DataTableCard>

    <!-- 任务摘要抽屉 -->
    <el-drawer v-model="detailDrawerVisible" title="任务详情" :size="drawerSize">
      <div v-if="detailTask" v-loading="detailLoading">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="任务ID">{{ detailTask.id }}</el-descriptions-item>
          <el-descriptions-item label="任务名称">{{ detailTask.name }}</el-descriptions-item>
          <el-descriptions-item label="任务类型">{{ detailTask.task_type }}</el-descriptions-item>
          <el-descriptions-item label="状态"><StatusTag :status="detailTask.status" /></el-descriptions-item>
          <el-descriptions-item label="进度">{{ detailTask.current_step || 0 }}/{{ detailTask.total_steps || 0 }} ({{ detailTask.progress_percentage || 0 }}%)</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ detailTask.duration_seconds != null ? detailTask.duration_seconds + 's' : '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDateTime(detailTask.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatDateTime(detailTask.start_time) }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ formatDateTime(detailTask.end_time) }}</el-descriptions-item>
        </el-descriptions>

        <el-row :gutter="12" style="margin-top:16px">
          <el-col :span="12">
            <div class="admin-tasks-page__summary-card">
              <h4>参数摘要</h4>
              <template v-if="configSummaryLines.length">
                <div v-for="(line, idx) in configSummaryLines" :key="idx" class="admin-tasks-page__summary-line">{{ line }}</div>
              </template>
              <span v-else class="admin-tasks-page__muted">暂无</span>
            </div>
          </el-col>
          <el-col :span="12">
            <div class="admin-tasks-page__summary-card">
              <h4>结果摘要</h4>
              <template v-if="detailTask.result_summary">
                <div class="admin-tasks-page__summary-line">结果总数: <strong>{{ detailTask.result_summary.total_results || 0 }}</strong></div>
                <div class="admin-tasks-page__summary-line">成功数: <strong class="admin-tasks-page__text-success">{{ detailTask.result_summary.success_count || 0 }}</strong></div>
                <div class="admin-tasks-page__summary-line">失败数: <strong class="admin-tasks-page__text-danger">{{ detailTask.result_summary.failed_count || 0 }}</strong></div>
                <div class="admin-tasks-page__summary-line">成功率: <strong>{{ detailTask.result_summary.success_rate || 0 }}%</strong></div>
              </template>
              <span v-else class="admin-tasks-page__muted">暂无结果</span>
            </div>
          </el-col>
        </el-row>

        <div style="margin-top:16px">
          <h4>任务配置</h4>
          <CodeBlock :content="detailTask.config || {}" />
        </div>

        <div style="margin-top:16px">
          <h4>任务日志</h4>
          <div class="admin-tasks-page__logs">
            <template v-if="recentLogLines.length">
              <div v-for="(line, idx) in recentLogLines" :key="idx" class="admin-tasks-page__log-line">{{ line }}</div>
            </template>
            <span v-else class="admin-tasks-page__muted">暂无日志</span>
          </div>
        </div>

        <div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">
          <el-button type="primary" @click="goTaskDetail(detailTask)">执行详情页</el-button>
          <el-button v-if="detailTask.status !== 'running'" type="success" @click="openEditTask(detailTask.id)">编辑任务</el-button>
          <el-button v-if="detailTask.status === 'running'" type="warning" @click="handleCancel(detailTask.id)">停止任务</el-button>
          <el-dropdown v-if="detailTask.status !== 'running'" @command="(cmd) => handleRestartCommand(cmd, detailTask)">
            <el-button type="success">
              重启任务<el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="resume">从断点重启</el-dropdown-item>
                <el-dropdown-item command="fresh">从头重启</el-dropdown-item>
                <el-dropdown-item command="create" divided>创建新重启任务</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button type="danger" @click="handleDelete(detailTask.id)">删除任务</el-button>
        </div>
      </div>
    </el-drawer>

    <!-- 创建任务弹窗 -->
    <el-dialog v-model="createDialogVisible" title="创建任务" :width="dialogWidth" :fullscreen="isMobile">
      <el-form :model="createForm" :label-width="formLabelWidth" :label-position="formLabelPosition">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="任务名称"><el-input v-model="createForm.name" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="任务类型">
              <el-select v-model="createForm.task_type" style="width:100%">
                <el-option v-for="opt in taskTypeOptions" :key="opt.value" :value="opt.value" :label="opt.label" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="任务描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="任务配置">
          <el-input v-model="createForm.config" type="textarea" :rows="10" spellcheck="false" placeholder="JSON 格式" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建并启动</el-button>
      </template>
    </el-dialog>

    <!-- 编辑任务弹窗 -->
    <el-dialog v-model="editDialogVisible" title="编辑任务" :width="dialogWidth" :fullscreen="isMobile">
      <el-form :model="editForm" :label-width="formLabelWidth" :label-position="formLabelPosition">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="任务名称"><el-input v-model="editForm.name" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="任务类型">
              <el-input :model-value="editForm.task_type" readonly />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="任务状态">
              <el-select v-model="editForm.status" style="width:100%">
                <el-option v-for="opt in taskStatusEditableOptions" :key="opt.value" :value="opt.value" :label="opt.label" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="任务描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="任务配置">
          <el-input v-model="editForm.config" type="textarea" :rows="14" spellcheck="false" placeholder="JSON 格式" />
        </el-form-item>
      </el-form>
      <el-alert
        title="正在运行的任务不允许修改；如需调整，请先停止任务。不能手动将任务改为运行中。"
        type="warning"
        :closable="false"
        show-icon
      />
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSaveEdit">保存修改</el-button>
      </template>
    </el-dialog>

    <!-- 批量重启弹窗 -->
    <el-dialog v-model="batchDialogVisible" title="批量重启任务" width="860px" :fullscreen="isMobile" @closed="resetBatchRestartState">
      <div class="admin-tasks-page__batch-summary">
        <div class="admin-tasks-page__batch-summary-head">
          <div class="admin-tasks-page__batch-summary-text">{{ batchSummaryText }}</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <el-button size="small" :disabled="batchRestarting" @click="selectAllRestartable">全选当前页</el-button>
            <el-button size="small" :disabled="batchRestarting" @click="clearBatchSelection">清空</el-button>
          </div>
        </div>
        <div class="admin-tasks-page__batch-progress">{{ batchProgressText }}</div>
      </div>

      <div style="margin:12px 0">
        <div style="font-weight:600;margin-bottom:8px">重启方式</div>
        <el-radio-group v-model="batchRestartMode" :disabled="batchRestarting">
          <el-radio-button value="resume">从断点重启</el-radio-button>
          <el-radio-button value="fresh">从头重启</el-radio-button>
        </el-radio-group>
      </div>

      <div v-loading="batchLoading" class="admin-tasks-page__batch-list">
        <div v-if="!batchTasks.length" class="admin-tasks-page__muted" style="text-align:center;padding:16px 0">当前页暂无任务</div>
        <div
          v-for="task in batchTasks"
          :key="task.id"
          class="admin-tasks-page__batch-card"
          :class="{
            'is-selected': batchSelectedIds.includes(task.id),
            'is-disabled': !isBatchRestartable(task),
            'is-success': batchResults[task.id]?.status === 'success',
            'is-error': batchResults[task.id]?.status === 'error',
          }"
          @click="toggleBatchTask(task)"
        >
          <el-checkbox
            :model-value="batchSelectedIds.includes(task.id)"
            :disabled="batchRestarting || !isBatchRestartable(task)"
            @click.stop
            @change="toggleBatchTask(task)"
          />
          <div class="admin-tasks-page__batch-card-main">
            <div class="admin-tasks-page__batch-card-title">{{ task.name || '未命名任务' }}</div>
            <div class="admin-tasks-page__batch-card-sub">{{ task.id }}</div>
            <div class="admin-tasks-page__batch-card-sub">{{ task.task_type || '-' }} · {{ formatDateTime(task.created_at) }}</div>
          </div>
          <div class="admin-tasks-page__batch-card-side">
            <StatusTag :status="task.status" />
            <div
              v-if="batchResults[task.id]"
              class="admin-tasks-page__batch-card-result"
              :class="batchResults[task.id].status === 'success' ? 'admin-tasks-page__text-success' : 'admin-tasks-page__text-danger'"
            >{{ batchResults[task.id].message }}</div>
            <div v-else-if="isBatchRestartable(task)" class="admin-tasks-page__muted">可重启</div>
            <div v-else class="admin-tasks-page__muted">运行中，不可批量重启</div>
          </div>
        </div>
      </div>

      <div class="admin-tasks-page__batch-footer-bar">
        <div style="display:flex;align-items:center;gap:8px">
          <span class="admin-tasks-page__muted">共 {{ batchTotal }} 条</span>
          <el-select v-model="batchPageSize" size="small" style="width:100px" :disabled="batchRestarting" @change="handleBatchPageSizeChange">
            <el-option :value="10" label="10 / 页" />
            <el-option :value="20" label="20 / 页" />
            <el-option :value="50" label="50 / 页" />
          </el-select>
        </div>
        <el-pagination
          v-model:current-page="batchPage"
          :page-size="batchPageSize"
          :total="batchTotal"
          :disabled="batchRestarting"
          layout="prev, pager, next"
          size="small"
          @current-change="loadBatchTasks"
        />
      </div>

      <template #footer>
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
          <span class="admin-tasks-page__muted" style="margin-right:auto">已选任务会逐个重启，单个失败不阻断后续任务。</span>
          <el-button @click="batchDialogVisible = false">取消</el-button>
          <el-button type="success" :loading="batchRestarting" :disabled="batchSelectedIds.length < 1" @click="restartSelectedBatchTasks">批量重启</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { getTasks, getTask, createTask, cancelTask, deleteTask, restartTask, createRestartTask, updateTaskConfig } from '@/api/task'
import { getTaskRuntimeDetail, getTaskStopConfirmation } from '@/api/admin'
import { getEnums } from '@/api/meta'
import { formatDateTime } from '@/utils/format'
import StatusTag from '@/components/StatusTag.vue'
import PageToolbar from '@/components/PageToolbar.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import DataTableCard from '@/components/DataTableCard.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'
import CodeBlock from '@/components/CodeBlock.vue'
import { useResponsive } from '@/composables/useResponsive'
import { usePolling } from '@/composables/usePolling'

const router = useRouter()
const { isMobile, componentSize, drawerSize, dialogWidth, formLabelPosition, formLabelWidth } = useResponsive()
const tasks = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const filters = ref({ status: '', task_type: '', keyword: '' })
const detailDrawerVisible = ref(false)
const detailTask = ref(null)
const detailLoading = ref(false)
const createDialogVisible = ref(false)
const creating = ref(false)
const createForm = reactive({ name: '', task_type: 'google_sheet', description: '', config: '' })
const editDialogVisible = ref(false)
const saving = ref(false)
const editingTaskId = ref(null)
const editForm = reactive({ name: '', task_type: '', status: 'pending', description: '', config: '' })

// 枚举（对齐静态版 /api/meta/enums：task_statuses / task_types / task_status_editable），加载失败时回退内置选项。
const DEFAULT_STATUS_OPTIONS = [
  { value: 'pending', label: '待执行' },
  { value: 'running', label: '运行中' },
  { value: 'completed', label: '已完成' },
  { value: 'cancelled', label: '已取消' },
  { value: 'error', label: '错误' },
]
const DEFAULT_TYPE_OPTIONS = [
  { value: 'google_sheet', label: 'Google Sheet' },
  { value: 'google_sheet_C4', label: 'Google Sheet C4' },
  { value: 'google_sheet_C5', label: 'Google Sheet C5' },
]
const DEFAULT_EDITABLE_STATUS_OPTIONS = [
  { value: 'pending', label: '待执行' },
  { value: 'completed', label: '已完成' },
  { value: 'cancelled', label: '已取消' },
  { value: 'error', label: '错误' },
]
const taskStatusOptions = ref(DEFAULT_STATUS_OPTIONS)
const taskTypeOptions = ref(DEFAULT_TYPE_OPTIONS)
const taskStatusEditableOptions = ref(DEFAULT_EDITABLE_STATUS_OPTIONS)

const filterConfig = computed(() => [
  {
    key: 'status',
    type: 'select',
    placeholder: '状态',
    span: { xs: 24, sm: 6, md: 4 },
    options: taskStatusOptions.value,
  },
  {
    key: 'task_type',
    type: 'select',
    placeholder: '类型',
    span: { xs: 24, sm: 6, md: 4 },
    options: taskTypeOptions.value,
  },
  {
    key: 'keyword',
    type: 'input',
    placeholder: '任务名称 / ID',
    span: { xs: 24, sm: 8, md: 6 },
  },
])

onMounted(async () => {
  try {
    const res = await getEnums()
    if (res?.task_statuses?.length) taskStatusOptions.value = res.task_statuses
    if (res?.task_types?.length) taskTypeOptions.value = res.task_types
    if (res?.task_status_editable?.length) taskStatusEditableOptions.value = res.task_status_editable
  } catch {
    // 枚举加载失败时沿用内置选项，不阻断页面
  }
})

async function loadTasks() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value }
    if (filters.value.status) params.status = filters.value.status
    if (filters.value.task_type) params.task_type = filters.value.task_type
    if (filters.value.keyword) params.keyword = filters.value.keyword
    const res = await getTasks(params)
    tasks.value = res.items || []
    total.value = res.total || 0
  } finally { loading.value = false }
}

function doFilter() { page.value = 1; loadTasks() }
function clearFilters() { filters.value = { status: '', task_type: '', keyword: '' }; doFilter() }

usePolling(loadTasks, { interval: 30000, immediate: true })

// ===== 详情跳转分流（对齐静态版 buildTaskDetailUrl，Vue 路由路径） =====
function normalizeTaskType(taskType) {
  const normalized = String(taskType || '').trim().toLowerCase()
  if (['google_sheet', 'google_sheet_c3', 'google_sheet_c31'].includes(normalized)) return 'google_sheet'
  if (normalized === 'google_sheet_c4') return 'google_sheet_c4'
  if (normalized === 'google_sheet_c5') return 'google_sheet_c5'
  if (['backtest_training', 'backtest'].includes(normalized)) return 'backtest_training'
  if (['backtest_multi_product', 'multi_product_backtest', 'backtest_multi'].includes(normalized)) return 'backtest_multi_product'
  return normalized
}

function getTaskVersionFromType(taskType) {
  const normalized = normalizeTaskType(taskType)
  if (normalized === 'google_sheet_c5') return 'c5'
  if (normalized === 'google_sheet_c4') return 'c4'
  if (normalized === 'google_sheet') return 'c3'
  return ''
}

function isGoogleSheetTask(taskType) {
  return ['google_sheet', 'google_sheet_c4', 'google_sheet_c5'].includes(normalizeTaskType(taskType))
}

function taskDetailRoute(task) {
  const normalized = normalizeTaskType(task?.task_type)
  if (normalized === 'backtest_training') return `/backtest/${task.id}`
  if (normalized === 'backtest_multi_product') return `/backtest-multi/${task.id}`
  return `/task/${task.id}`
}

function goTaskDetail(task) {
  if (!task?.id) return
  detailDrawerVisible.value = false
  router.push(taskDetailRoute(task))
}

// ===== 停止确认 badge =====
function stopBadgeInfo(status) {
  if (status === 'running') return { text: '运行中', type: 'warning' }
  if (['cancelled', 'completed', 'error', 'pending'].includes(status)) return { text: '线程已结束', type: 'success' }
  return { text: '未知', type: 'info' }
}

// ===== 详情抽屉 =====
async function showDetail(id) {
  detailDrawerVisible.value = true
  detailLoading.value = true
  detailTask.value = null
  try {
    const res = await getTaskRuntimeDetail(id)
    detailTask.value = res.task || null
  } catch {
    const res = await getTask(id)
    detailTask.value = res.task || res
  } finally { detailLoading.value = false }
}

const configSummaryLines = computed(() => {
  const summary = detailTask.value?.config_summary
  if (!summary) return []
  const lines = [`参数组数: ${summary.parameter_groups || 0}`]
  lines.push(`参数规模: ${(summary.parameter_sizes || []).join(', ') || '-'}`)
  if (summary.sheet_name) lines.push(`Sheet: ${summary.sheet_name}`)
  if (summary.token_id) lines.push(`Token ID: ${summary.token_id}`)
  if (summary.parameter_preview?.length) {
    summary.parameter_preview.forEach((item) => {
      lines.push(`组 ${item.group}: ${JSON.stringify(item.sample)}`)
    })
  }
  return lines
})

const recentLogLines = computed(() => {
  const logs = detailTask.value?.recent_logs
  if (!Array.isArray(logs) || !logs.length) return []
  return logs.map((log) => `[${formatDateTime(log.timestamp)}] ${log.message || ''}`)
})

function refreshDetailIfShowing(id) {
  if (detailDrawerVisible.value && detailTask.value?.id === id) showDetail(id)
}

async function handleCancel(id) {
  await ElMessageBox.confirm('确定要停止这个任务吗？', '确认停止', { type: 'warning' })
  await cancelTask(id)
  pollStopConfirmation(id)
}

// 停止后轮询确认任务已完全停止（对齐静态版：最多 8 次 × 800ms）
async function pollStopConfirmation(id, attempt = 0) {
  try {
    const res = await getTaskStopConfirmation(id)
    if (res?.stop_confirmed) {
      ElMessage.success('任务已完全停止')
      loadTasks()
      refreshDetailIfShowing(id)
      return
    }
    if (attempt < 8) {
      setTimeout(() => pollStopConfirmation(id, attempt + 1), 800)
      return
    }
    ElMessage.warning('已发送停止请求，任务仍在退出中')
    loadTasks()
    refreshDetailIfShowing(id)
  } catch (e) {
    ElMessage.error(e.message || '停止确认检查失败')
  }
}

async function handleRestart(id, resumeFromCheckpoint) {
  await restartTask(id, { resume_from_checkpoint: resumeFromCheckpoint })
  ElMessage.success('任务重启成功')
  loadTasks()
  refreshDetailIfShowing(id)
}

function handleRestartCommand(cmd, task) {
  if (!task?.id) return
  if (cmd === 'create') {
    handleCreateRestartTask(task)
    return
  }
  handleRestart(task.id, cmd === 'resume')
}

// 创建新重启任务：Google Sheet 系跳创建页回填，其余类型调 create-restart 后跳新任务详情
async function handleCreateRestartTask(task) {
  const id = task.id
  const taskType = task.task_type
  if (isGoogleSheetTask(taskType)) {
    detailDrawerVisible.value = false
    router.push(`/task/create/${getTaskVersionFromType(taskType) || 'c3'}?restart_task_id=${encodeURIComponent(id)}`)
    return
  }
  try {
    const res = await createRestartTask(id)
    ElMessage.success(res?.message || '新重启任务创建成功')
    const nextTaskId = res?.new_task_id || id
    detailDrawerVisible.value = false
    router.push(taskDetailRoute({ id: nextTaskId, task_type: taskType }))
  } catch (e) {
    ElMessage.error(e.message || '创建重启任务失败')
  }
}

async function handleDelete(id) {
  await ElMessageBox.confirm('确定要删除这个任务吗？删除后不可恢复。', '确认删除', { type: 'warning' })
  await deleteTask(id)
  ElMessage.success('任务已删除')
  detailDrawerVisible.value = false
  loadTasks()
}

// ===== 创建任务 =====
function openCreate() {
  Object.assign(createForm, { name: '', task_type: 'google_sheet', description: '', config: '' })
  createDialogVisible.value = true
}

async function handleCreate() {
  if (!createForm.name || !createForm.config) { ElMessage.warning('请填写必要字段'); return }
  try { JSON.parse(createForm.config) } catch { ElMessage.error('配置格式错误'); return }
  creating.value = true
  try {
    await createTask({ name: createForm.name, task_type: createForm.task_type, description: createForm.description, config: JSON.parse(createForm.config) })
    ElMessage.success('任务创建成功')
    createDialogVisible.value = false
    loadTasks()
  } catch (e) { ElMessage.error(e.message || '任务创建失败') }
  finally { creating.value = false }
}

// ===== 编辑任务 =====
async function openEditTask(id) {
  const rowTask = tasks.value.find((task) => task.id === id)
  if (rowTask?.status === 'running') {
    ElMessage.warning('正在运行的任务不允许修改，请先停止任务')
    return
  }
  try {
    const res = await getTask(id)
    const target = res?.task || res
    if (target?.status === 'running') {
      ElMessage.warning('正在运行的任务不允许修改，请先停止任务')
      return
    }
    editingTaskId.value = id
    editForm.name = target?.name || ''
    editForm.task_type = target?.task_type || ''
    editForm.status = DEFAULT_EDITABLE_STATUS_OPTIONS.some((opt) => opt.value === target?.status)
      ? target.status
      : 'pending'
    editForm.description = target?.description || ''
    editForm.config = JSON.stringify(target?.config || {}, null, 2)
    editDialogVisible.value = true
  } catch (e) {
    ElMessage.error(e.message || '获取任务信息失败')
  }
}

async function handleSaveEdit() {
  if (!editingTaskId.value) return
  if (!editForm.name || !editForm.config) {
    ElMessage.error('请填写任务名称和配置 JSON')
    return
  }
  let config
  try {
    config = JSON.parse(editForm.config)
  } catch (e) {
    ElMessage.error(`配置 JSON 格式错误: ${e.message}`)
    return
  }
  saving.value = true
  try {
    await updateTaskConfig(editingTaskId.value, {
      name: editForm.name,
      description: editForm.description,
      status: editForm.status,
      config,
    })
    ElMessage.success('任务已更新')
    editDialogVisible.value = false
    loadTasks()
    refreshDetailIfShowing(editingTaskId.value)
  } catch (e) {
    ElMessage.error(e.message || '更新任务失败')
  } finally {
    saving.value = false
  }
}

// ===== 批量重启 =====
const batchDialogVisible = ref(false)
const batchTasks = ref([])
const batchLoading = ref(false)
const batchPage = ref(1)
const batchPageSize = ref(10)
const batchTotal = ref(0)
const batchSelectedIds = ref([])
const batchResults = ref({})
const batchRestarting = ref(false)
const batchRestartMode = ref('resume')
const batchProgressText = ref('尚未开始重启')
const batchTaskCache = new Map()

function isBatchRestartable(task) {
  return task && task.status !== 'running'
}

const batchSummaryText = computed(() => {
  const restartableCount = batchTasks.value.filter(isBatchRestartable).length
  const successes = Object.values(batchResults.value).filter((r) => r.status === 'success').length
  const failures = Object.values(batchResults.value).filter((r) => r.status === 'error').length
  return `当前页 ${batchTasks.value.length} 个任务，可重启 ${restartableCount} 个，已选 ${batchSelectedIds.value.length} 个，成功 ${successes} 个，失败 ${failures} 个`
})

function resetBatchRestartState() {
  if (batchRestarting.value) return
  batchTasks.value = []
  batchPage.value = 1
  batchSelectedIds.value = []
  batchResults.value = {}
  batchRestarting.value = false
  batchProgressText.value = '尚未开始重启'
}

function openBatchRestart() {
  batchTasks.value = []
  batchPage.value = 1
  batchSelectedIds.value = []
  batchResults.value = {}
  batchRestarting.value = false
  batchProgressText.value = '尚未开始重启'
  batchDialogVisible.value = true
  loadBatchTasks(1)
}

async function loadBatchTasks(pageNum = batchPage.value) {
  batchLoading.value = true
  try {
    const res = await getTasks({ page: pageNum, per_page: batchPageSize.value })
    batchTasks.value = res.items || []
    batchTasks.value.forEach((task) => batchTaskCache.set(String(task.id), task))
    batchPage.value = pageNum
    batchTotal.value = res.total || 0
  } catch (e) {
    batchTasks.value = []
    batchTotal.value = 0
    ElMessage.error(e.message || '获取批量重启任务列表失败')
  } finally { batchLoading.value = false }
}

function handleBatchPageSizeChange() {
  batchPage.value = 1
  loadBatchTasks(1)
}

function toggleBatchTask(task) {
  if (batchRestarting.value || !isBatchRestartable(task)) return
  const idx = batchSelectedIds.value.indexOf(task.id)
  if (idx >= 0) batchSelectedIds.value.splice(idx, 1)
  else batchSelectedIds.value.push(task.id)
}

function selectAllRestartable() {
  if (batchRestarting.value) return
  batchTasks.value.filter(isBatchRestartable).forEach((task) => {
    if (!batchSelectedIds.value.includes(task.id)) batchSelectedIds.value.push(task.id)
  })
}

function clearBatchSelection() {
  if (batchRestarting.value) return
  batchSelectedIds.value = []
  batchResults.value = {}
  batchProgressText.value = '尚未开始重启'
}

async function restartSelectedBatchTasks() {
  if (batchRestarting.value || batchSelectedIds.value.length < 1) return
  const taskIds = [...batchSelectedIds.value]
  const resumeFromCheckpoint = batchRestartMode.value !== 'fresh'
  const confirmMessage = resumeFromCheckpoint
    ? `确定要从断点批量重启 ${taskIds.length} 个任务吗？`
    : `确定要从头批量重启 ${taskIds.length} 个任务吗？从头重启会清空对应任务的历史结果。`
  try {
    await ElMessageBox.confirm(confirmMessage, '确认批量重启', { type: 'warning' })
  } catch {
    return
  }

  let successCount = 0
  let failureCount = 0
  batchRestarting.value = true
  batchResults.value = {}

  for (let index = 0; index < taskIds.length; index++) {
    const taskId = taskIds[index]
    batchProgressText.value = `正在重启第 ${index + 1}/${taskIds.length} 个任务`
    try {
      const res = await restartTask(taskId, { resume_from_checkpoint: resumeFromCheckpoint })
      successCount += 1
      batchResults.value[taskId] = { status: 'success', message: res?.message || '重启成功' }
    } catch (e) {
      failureCount += 1
      batchResults.value[taskId] = { status: 'error', message: e.message || '重启失败' }
    }
  }

  batchRestarting.value = false
  batchSelectedIds.value = []
  batchProgressText.value = `批量重启完成：成功 ${successCount} 个，失败 ${failureCount} 个`
  loadTasks()
  if (failureCount) ElMessage.warning(`批量重启完成：成功 ${successCount} 个，失败 ${failureCount} 个`)
  else ElMessage.success(`批量重启完成：成功 ${successCount} 个，失败 ${failureCount} 个`)
}
</script>

<style scoped>
.admin-tasks-page__sub-id {
  font-size: var(--app-font-xs);
  color: var(--app-text-muted);
}

.admin-tasks-page__summary-card {
  border: 1px solid var(--app-border);
  border-radius: 8px;
  padding: 12px;
  background: var(--app-surface-elevated, transparent);
  height: 100%;
}

.admin-tasks-page__summary-card h4 {
  margin: 0 0 8px;
  font-size: var(--app-font-sm);
}

.admin-tasks-page__summary-line {
  font-size: var(--app-font-xs);
  color: var(--app-text-soft, var(--app-text));
  line-height: 1.8;
  word-break: break-all;
}

.admin-tasks-page__muted {
  color: var(--app-text-muted);
  font-size: var(--app-font-xs);
}

.admin-tasks-page__text-success {
  color: #16a34a;
}

.admin-tasks-page__text-danger {
  color: #ef4444;
}

.admin-tasks-page__logs {
  max-height: 220px;
  overflow: auto;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  padding: 10px 12px;
  background: #0b1220;
}

.admin-tasks-page__log-line {
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.7;
  color: #93c5fd;
  white-space: pre-wrap;
  word-break: break-all;
}

.admin-tasks-page__batch-summary {
  border: 1px solid var(--app-border);
  border-radius: 8px;
  padding: 12px;
  background: var(--app-surface-elevated, transparent);
}

.admin-tasks-page__batch-summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.admin-tasks-page__batch-summary-text {
  font-weight: 600;
  font-size: var(--app-font-sm);
}

.admin-tasks-page__batch-progress {
  margin-top: 8px;
  font-size: var(--app-font-xs);
  color: var(--app-text-muted);
}

.admin-tasks-page__batch-list {
  max-height: 360px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 80px;
}

.admin-tasks-page__batch-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  padding: 10px 12px;
  cursor: pointer;
}

.admin-tasks-page__batch-card.is-selected {
  border-color: var(--el-color-primary);
}

.admin-tasks-page__batch-card.is-disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.admin-tasks-page__batch-card.is-success {
  border-color: var(--el-color-success);
}

.admin-tasks-page__batch-card.is-error {
  border-color: var(--el-color-danger);
}

.admin-tasks-page__batch-card-main {
  flex: 1;
  min-width: 0;
}

.admin-tasks-page__batch-card-title {
  font-weight: 600;
  font-size: var(--app-font-sm);
}

.admin-tasks-page__batch-card-sub {
  font-size: var(--app-font-xs);
  color: var(--app-text-muted);
  word-break: break-all;
}

.admin-tasks-page__batch-card-side {
  text-align: right;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.admin-tasks-page__batch-card-result {
  font-size: var(--app-font-xs);
  word-break: break-all;
  max-width: 220px;
}

.admin-tasks-page__batch-footer-bar {
  margin-top: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
</style>
