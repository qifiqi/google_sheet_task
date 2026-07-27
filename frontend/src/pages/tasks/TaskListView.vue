<script setup lang="ts">
import { onMounted, reactive, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import BatchRestartDialog from '../../components/tasks/BatchRestartDialog.vue'
import TaskDetailDrawer from '../../components/tasks/TaskDetailDrawer.vue'
import TaskEditDialog from '../../components/tasks/TaskEditDialog.vue'
import TaskListTable from '../../components/tasks/TaskListTable.vue'
import { requestJson } from '../../api/http'
import { useAuthStore } from '../../stores/auth'
import type { PaginationState, TaskItem, TaskListResponse, TaskLogItem, TaskStatistics } from '../../types/api'
import { taskExecutionUrl } from '../../utils/task'

const auth = useAuthStore()
const router = useRouter()
const items = shallowRef<TaskItem[]>([])
const loading = shallowRef(false)
const errorMessage = shallowRef('')
const detailVisible = shallowRef(false)
const selectedTask = shallowRef<TaskItem | null>(null)
const selectedTasks = shallowRef<TaskItem[]>([])
const taskLogs = shallowRef<TaskLogItem[]>([])
const logsLoading = shallowRef(false)
const batchRestartVisible = shallowRef(false)
const batchRestarting = shallowRef(false)
const editVisible = shallowRef(false)
const editingTask = shallowRef<TaskItem | null>(null)
const savingTask = shallowRef(false)
const filters = reactive({ keyword: '', status: '', taskType: '' })
const pagination = reactive<PaginationState>({ page: 1, per_page: 10, total: 0, pages: 0 })
const statistics = reactive<TaskStatistics>({
  total_tasks: 0, completed_tasks: 0, running_tasks: 0, error_tasks: 0,
  pending_tasks: 0, today_new_tasks: 0, success_rate: 0, error_rate: 0, avg_duration_minutes: 0,
})

const taskTypes = [
  { value: 'google_sheet', label: 'Google Sheet C3' },
  { value: 'google_sheet_C4', label: 'Google Sheet C4' },
  { value: 'google_sheet_C5', label: 'Google Sheet C5' },
  { value: 'google_sheet_C7', label: 'Google Sheet C7' },
  { value: 'backtest_training', label: '单品数据回测' },
  { value: 'backtest_multi_product', label: '多品数据回测' },
]

function can(permission: string) {
  return auth.hasPermission(permission)
}

async function loadTasks(page = pagination.page) {
  loading.value = true
  errorMessage.value = ''
  selectedTasks.value = []
  const params = new URLSearchParams({ page: String(page), per_page: String(pagination.per_page) })
  if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
  if (filters.status) params.set('status', filters.status)
  if (filters.taskType) params.set('task_type', filters.taskType)

  try {
    const data = await requestJson<TaskListResponse>(`/api/tasks?${params}`)
    items.value = data.tasks
    Object.assign(pagination, data.pagination)
    Object.assign(statistics, data.statistics)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '加载任务失败'
  } finally {
    loading.value = false
  }
}

function search() { loadTasks(1) }

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  filters.taskType = ''
  loadTasks(1)
}

async function openDetail(task: TaskItem) {
  selectedTask.value = task
  detailVisible.value = true
  taskLogs.value = []
  logsLoading.value = true
  const [runtime, logs] = await Promise.allSettled([
    requestJson<{ success: boolean; task: TaskItem }>(`/admin/api/tasks/${encodeURIComponent(task.id)}/runtime-detail`),
    requestJson<{ status: string; logs: TaskLogItem[] }>(`/api/tasks/${encodeURIComponent(task.id)}/logs`),
  ])
  logsLoading.value = false
  if (runtime.status === 'fulfilled') selectedTask.value = runtime.value.task
  else ElMessage.warning(runtime.reason instanceof Error ? runtime.reason.message : '未能加载运行详情')
  if (logs.status === 'fulfilled') taskLogs.value = logs.value.logs
}

async function cancelTask(task: TaskItem) {
  await ElMessageBox.confirm(`确定停止“${task.name}”吗？`, '停止任务', { type: 'warning', confirmButtonText: '停止' })
  await requestJson(`/api/tasks/${encodeURIComponent(task.id)}/cancel`, { method: 'POST' })
  ElMessage.success('已发送停止请求')
  loadTasks()
}

async function restartTask(task: TaskItem, resumeFromCheckpoint = true) {
  await ElMessageBox.confirm(`确定${resumeFromCheckpoint ? '从断点' : '从头'}重启“${task.name}”吗？`, '重启任务', { type: 'warning', confirmButtonText: '重启' })
  await requestJson(`/api/tasks/${encodeURIComponent(task.id)}/restart`, {
    method: 'POST', body: JSON.stringify({ resume_from_checkpoint: resumeFromCheckpoint }),
  })
  ElMessage.success('任务已提交重启')
  loadTasks()
}

async function openEdit(task: TaskItem) {
  if (task.status === 'running') {
    ElMessage.warning('正在运行的任务不能编辑，请先停止任务')
    return
  }
  try {
    const data = await requestJson<{ status: string; task: TaskItem }>(`/api/tasks/${encodeURIComponent(task.id)}`)
    editingTask.value = data.task
    editVisible.value = true
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载任务配置失败') }
}

async function saveTaskEdit(payload: { id: string; name: string; description: string; status: string; config: Record<string, unknown> }) {
  savingTask.value = true
  try {
    await requestJson(`/api/tasks/${encodeURIComponent(payload.id)}/config`, { method: 'PUT', body: JSON.stringify(payload) })
    ElMessage.success('任务已更新')
    editVisible.value = false
    loadTasks()
    if (selectedTask.value?.id === payload.id) openDetail({ ...selectedTask.value, ...payload })
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '更新任务失败') } finally { savingTask.value = false }
}

function googleSheetTaskRoute(task: TaskItem) {
  const routes: Record<string, { detail: 'C3TaskDetail' | 'C4TaskDetail' | 'C5TaskDetail' | 'C7TaskDetail'; create: 'C3TaskCreate' | 'C4TaskCreate' | 'C5TaskCreate' | 'C7TaskCreate' }> = {
    google_sheet: { detail: 'C3TaskDetail', create: 'C3TaskCreate' },
    google_sheet_c4: { detail: 'C4TaskDetail', create: 'C4TaskCreate' },
    google_sheet_c5: { detail: 'C5TaskDetail', create: 'C5TaskCreate' },
    google_sheet_c7: { detail: 'C7TaskDetail', create: 'C7TaskCreate' },
  }
  return routes[String(task.task_type || '').toLowerCase()]
}

function viewTaskDetail(task: TaskItem) {
  const target = googleSheetTaskRoute(task)
  if (target) {
    void router.push({ name: target.detail, params: { taskId: task.id } })
    return
  }
  void openDetail(task)
}

function viewExecution(task: TaskItem) {
  const target = googleSheetTaskRoute(task)
  if (target) {
    void router.push({ name: target.detail, params: { taskId: task.id } })
    return
  }
  window.location.assign(taskExecutionUrl(task))
}

async function createRestartTask(task: TaskItem) {
  const target = googleSheetTaskRoute(task)
  if (target) {
    void router.push({ name: target.create, query: { restart_task_id: task.id } })
    return
  }
  await ElMessageBox.confirm(`确定基于“${task.name}”创建并启动新任务吗？`, '创建重启任务', { type: 'warning', confirmButtonText: '创建并启动' })
  const response = await requestJson<{ status: string; new_task_id: string; message?: string }>(`/api/tasks/${encodeURIComponent(task.id)}/create-restart`, { method: 'POST' })
  ElMessage.success(response.message || '重启任务已创建')
  window.location.assign(taskExecutionUrl({ ...task, id: response.new_task_id }))
}

function wait(milliseconds: number) {
  return new Promise(resolve => window.setTimeout(resolve, milliseconds))
}

async function restartSelectedTasks(options: { resumeFromCheckpoint: boolean; delaySeconds: number }) {
  batchRestarting.value = true
  let restarted = 0
  const failures: string[] = []

  try {
    for (const [index, task] of selectedTasks.value.entries()) {
      try {
        await requestJson(`/api/tasks/${encodeURIComponent(task.id)}/restart`, {
          method: 'POST',
          body: JSON.stringify({ resume_from_checkpoint: options.resumeFromCheckpoint }),
        })
        restarted += 1
      } catch (error) {
        failures.push(`${task.name}: ${error instanceof Error ? error.message : '重启失败'}`)
      }

      if (index < selectedTasks.value.length - 1) {
        await wait(options.delaySeconds * 1000)
      }
    }

    if (failures.length) {
      ElMessage.warning(`已提交 ${restarted} 个任务重启，${failures.length} 个失败：${failures.join('；')}`)
    } else {
      ElMessage.success(`已依次提交 ${restarted} 个任务重启`)
    }
    batchRestartVisible.value = false
    loadTasks()
  } finally {
    batchRestarting.value = false
  }
}

async function removeTask(task: TaskItem) {
  await ElMessageBox.confirm(`删除“${task.name}”后无法恢复，是否继续？`, '删除任务', { type: 'error', confirmButtonText: '删除' })
  await requestJson(`/api/tasks/${encodeURIComponent(task.id)}`, { method: 'DELETE' })
  ElMessage.success('任务已删除')
  loadTasks(items.value.length === 1 && pagination.page > 1 ? pagination.page - 1 : pagination.page)
}

function openTaskCreator() {
  void router.push({ name: 'C3Tasks' })
}

onMounted(loadTasks)
</script>

<template>
  <section class="task-page">
    <header class="task-page__header">
      <div>
        <p>任务模块</p>
        <h1>任务管理</h1>
      </div>
      <el-button v-if="can('task:create')" type="primary" :icon="Plus" @click="openTaskCreator">新建任务</el-button>
    </header>

    <div class="task-page__metrics" aria-label="任务统计">
      <div><span>任务总数</span><strong>{{ statistics.total_tasks }}</strong></div>
      <div><span>运行中</span><strong class="is-success">{{ statistics.running_tasks }}</strong></div>
      <div><span>待执行</span><strong class="is-primary">{{ statistics.pending_tasks }}</strong></div>
      <div><span>异常任务</span><strong class="is-danger">{{ statistics.error_tasks }}</strong></div>
    </div>

    <section class="task-page__table-panel">
      <div class="task-page__toolbar">
        <el-input v-model="filters.keyword" clearable placeholder="搜索任务名称" @keyup.enter="search" />
        <el-select v-model="filters.status" clearable placeholder="全部状态">
          <el-option label="待执行" value="pending" /><el-option label="运行中" value="running" />
          <el-option label="已完成" value="completed" /><el-option label="执行出错" value="error" />
          <el-option label="已取消" value="cancelled" />
        </el-select>
        <el-select v-model="filters.taskType" clearable placeholder="全部类型">
          <el-option v-for="item in taskTypes" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <div class="task-page__toolbar-actions">
          <el-button v-if="can('task:restart')" :disabled="selectedTasks.length === 0" @click="batchRestartVisible = true">批量重启<span v-if="selectedTasks.length">（{{ selectedTasks.length }}）</span></el-button>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
          <el-button text :icon="Refresh" aria-label="刷新任务列表" @click="() => loadTasks()" />
        </div>
      </div>
      <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" />
      <TaskListTable
        :items="items" :loading="loading" :can-cancel="can('task:cancel')" :can-restart="can('task:restart')" :can-delete="can('task:delete')" :can-edit="can('task:create')"
        @selection-change="selectedTasks = $event" @view="viewTaskDetail" @cancel="cancelTask" @restart="restartTask" @restart-fresh="(task) => restartTask(task, false)" @create-restart="createRestartTask" @edit="openEdit" @view-execution="viewExecution" @remove="removeTask"
      />
      <footer class="task-page__pagination">
        <span>共 {{ pagination.total }} 条</span>
        <el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.per_page" background layout="total, sizes, prev, pager, next, jumper" :page-sizes="[10, 20, 50]" :total="pagination.total" @current-change="loadTasks" @size-change="() => loadTasks(1)" />
      </footer>
    </section>
    <TaskDetailDrawer v-model="detailVisible" :task="selectedTask" :logs="taskLogs" :logs-loading="logsLoading" :can-edit="can('task:create')" :can-restart="can('task:restart')" @edit="openEdit" @view-execution="viewExecution" @restart-fresh="(task) => restartTask(task, false)" @create-restart="createRestartTask" />
    <BatchRestartDialog v-model="batchRestartVisible" :tasks="selectedTasks" :submitting="batchRestarting" @submit="restartSelectedTasks" />
    <TaskEditDialog v-model="editVisible" :task="editingTask" :submitting="savingTask" @save="saveTaskEdit" />
  </section>
</template>

<style scoped>
.task-page { display: grid; gap: 16px; }
.task-page__header { display: flex; align-items: end; justify-content: space-between; gap: 16px; }
.task-page__header p { margin: 0 0 2px; color: var(--admin-text-muted); font-size: 13px; }
.task-page__header h1 { margin: 0; color: var(--admin-text); font-size: 20px; font-weight: 600; }
.task-page__metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }
.task-page__metrics div { display: grid; gap: 5px; padding: 16px 20px; border-right: 1px solid var(--admin-border-light); }
.task-page__metrics div:last-child { border-right: 0; }
.task-page__metrics span { color: var(--admin-text-muted); font-size: 13px; }
.task-page__metrics strong { color: var(--admin-text); font-size: 24px; font-weight: 600; }
.task-page__metrics .is-success { color: var(--admin-success); }.task-page__metrics .is-primary { color: var(--admin-primary); }.task-page__metrics .is-danger { color: var(--admin-danger); }
.task-page__table-panel { display: grid; gap: 16px; padding: 16px 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }
.task-page__toolbar { display: flex; flex-wrap: wrap; gap: 10px; }.task-page__toolbar :deep(.el-input),.task-page__toolbar :deep(.el-select) { width: 210px; }.task-page__toolbar-actions { display: flex; gap: 8px; margin-left: auto; }
.task-page__pagination { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--admin-text-muted); font-size: 13px; }
@media (max-width: 900px) { .task-page__metrics { grid-template-columns: repeat(2, 1fr); }.task-page__metrics div:nth-child(2) { border-right: 0; }.task-page__metrics div:nth-child(-n+2) { border-bottom: 1px solid var(--admin-border-light); }.task-page__toolbar-actions { margin-left: 0; }.task-page__pagination { align-items: start; flex-direction: column; }.task-page__pagination :deep(.el-pagination) { flex-wrap: wrap; } }
@media (max-width: 560px) { .task-page__metrics { grid-template-columns: 1fr; }.task-page__metrics div { border-right: 0; border-bottom: 1px solid var(--admin-border-light); }.task-page__metrics div:last-child { border-bottom: 0; }.task-page__toolbar :deep(.el-input),.task-page__toolbar :deep(.el-select) { width: 100%; } }
</style>
