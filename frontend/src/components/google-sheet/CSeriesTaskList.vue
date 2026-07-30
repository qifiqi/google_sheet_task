<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DocumentCopy, Download, Plus, Refresh } from '@element-plus/icons-vue'
import BatchRestartDialog from '../tasks/BatchRestartDialog.vue'
import TaskListTable from '../tasks/TaskListTable.vue'
import { requestJson } from '../../api/http'
import { useAuthStore } from '../../stores/auth'
import type { PaginationState, TaskItem, TaskListResponse, TaskStatistics } from '../../types/api'

const props = withDefaults(defineProps<{
  title: string
  taskType: string
  createUrl: string
  batchCreateUrl?: string
  mergeExportUrl?: string
}>(), {
  batchCreateUrl: '',
  mergeExportUrl: '',
})

const auth = useAuthStore()
const router = useRouter()
const items = shallowRef<TaskItem[]>([])
const selectedTasks = shallowRef<TaskItem[]>([])
const loading = shallowRef(false)
const errorMessage = shallowRef('')
const navigatingUrl = shallowRef('')
const batchRestartVisible = shallowRef(false)
const batchRestarting = shallowRef(false)
const routePrefetches = new Map<string, Promise<void>>()
let idlePrefetchId: number | undefined
let prefetchTimerId: number | undefined
const filters = reactive({ keyword: '', status: '' })
const pagination = reactive<PaginationState>({ page: 1, per_page: 10, total: 0, pages: 0 })
const statistics = reactive<TaskStatistics>({
  total_tasks: 0,
  completed_tasks: 0,
  running_tasks: 0,
  error_tasks: 0,
  pending_tasks: 0,
  today_new_tasks: 0,
  success_rate: 0,
  error_rate: 0,
  avg_duration_minutes: 0,
})

function can(permission: string) {
  return auth.hasPermission(permission)
}

async function loadTasks(page = pagination.page) {
  loading.value = true
  errorMessage.value = ''
  selectedTasks.value = []
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(pagination.per_page),
    task_type: props.taskType,
  })

  if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
  if (filters.status) params.set('status', filters.status)

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

function search() {
  void loadTasks(1)
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  void loadTasks(1)
}

function prefetchUrl(url: string) {
  if (!url) return Promise.resolve()

  const pending = routePrefetches.get(url)
  if (pending) return pending

  const loaders = router.resolve(url).matched.flatMap(record => (
    Object.values(record.components || {}).filter(
      (component): component is () => Promise<unknown> => typeof component === 'function',
    )
  ))
  const prefetch = Promise.all(
    loaders.map(loader => Promise.resolve().then(() => loader())),
  ).then(() => undefined).catch(() => {
    routePrefetches.delete(url)
  })

  routePrefetches.set(url, prefetch)
  return prefetch
}

function scheduleTaskCreatorPrefetch() {
  const requestIdleCallback = (window as { requestIdleCallback?: Window['requestIdleCallback'] }).requestIdleCallback
  if (requestIdleCallback) {
    idlePrefetchId = requestIdleCallback.call(window, () => {
      idlePrefetchId = undefined
      void prefetchUrl(props.createUrl)
    }, { timeout: 1500 })
    return
  }

  prefetchTimerId = window.setTimeout(() => {
    prefetchTimerId = undefined
    void prefetchUrl(props.createUrl)
  }, 250)
}

async function openUrl(url: string) {
  if (!url || navigatingUrl.value) return

  navigatingUrl.value = url
  try {
    await router.push(url)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '页面跳转失败')
  } finally {
    navigatingUrl.value = ''
  }
}

async function openTaskCreator() {
  await openUrl(props.createUrl)
}

async function openBatchCreator() {
  if (props.batchCreateUrl) await openUrl(props.batchCreateUrl)
}

async function openMergeExporter() {
  if (props.mergeExportUrl) await openUrl(props.mergeExportUrl)
}

function taskRoute(task: TaskItem) {
  const routes: Record<string, { detail: 'C3TaskDetail' | 'C4TaskDetail' | 'C5TaskDetail' | 'C7TaskDetail'; create: 'C3TaskCreate' | 'C4TaskCreate' | 'C5TaskCreate' | 'C7TaskCreate' }> = {
    google_sheet: { detail: 'C3TaskDetail', create: 'C3TaskCreate' },
    google_sheet_c4: { detail: 'C4TaskDetail', create: 'C4TaskCreate' },
    google_sheet_c5: { detail: 'C5TaskDetail', create: 'C5TaskCreate' },
    google_sheet_c7: { detail: 'C7TaskDetail', create: 'C7TaskCreate' },
  }
  return routes[String(task.task_type || '').toLowerCase()]
}

function viewTask(task: TaskItem) {
  const target = taskRoute(task)
  if (target) {
    void router.push({ name: target.detail, params: { taskId: task.id } })
    return
  }
  ElMessage.error('当前任务类型没有 Vue 详情页')
}

function createRestartTask(task: TaskItem) {
  const target = taskRoute(task)
  if (target) {
    void router.push({ name: target.create, query: { restart_task_id: task.id } })
    return
  }
  ElMessage.error('当前任务类型没有 Vue 创建页')
}

async function cancelTask(task: TaskItem) {
  try {
    await ElMessageBox.confirm(`确定停止“${task.name}”吗？`, '停止任务', {
      type: 'warning',
      confirmButtonText: '停止',
    })
    await requestJson(`/api/tasks/${encodeURIComponent(task.id)}/cancel`, { method: 'POST' })
    ElMessage.success('已发送停止请求')
    await loadTasks()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error instanceof Error ? error.message : '停止任务失败')
  }
}

async function restartTask(task: TaskItem, resumeFromCheckpoint = true) {
  try {
    await ElMessageBox.confirm(`确定${resumeFromCheckpoint ? '从断点' : '从头'}重启“${task.name}”吗？`, '重启任务', {
      type: 'warning',
      confirmButtonText: '重启',
    })
    await requestJson(`/api/tasks/${encodeURIComponent(task.id)}/restart`, {
      method: 'POST',
      body: JSON.stringify({ resume_from_checkpoint: resumeFromCheckpoint }),
    })
    ElMessage.success('任务已提交重启')
    await loadTasks()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error instanceof Error ? error.message : '重启任务失败')
  }
}

async function removeTask(task: TaskItem) {
  try {
    await ElMessageBox.confirm(`删除“${task.name}”后无法恢复，是否继续？`, '删除任务', {
      type: 'error',
      confirmButtonText: '删除',
    })
    await requestJson(`/api/tasks/${encodeURIComponent(task.id)}`, { method: 'DELETE' })
    ElMessage.success('任务已删除')
    await loadTasks(items.value.length === 1 && pagination.page > 1 ? pagination.page - 1 : pagination.page)
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error instanceof Error ? error.message : '删除任务失败')
  }
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

      if (index < selectedTasks.value.length - 1) await wait(options.delaySeconds * 1000)
    }

    ElMessage[failures.length ? 'warning' : 'success'](
      failures.length
        ? `已提交 ${restarted} 个任务重启，${failures.length} 个失败`
        : `已依次提交 ${restarted} 个任务重启`,
    )
    batchRestartVisible.value = false
    await loadTasks()
  } finally {
    batchRestarting.value = false
  }
}

onMounted(() => {
  void loadTasks()
  if (can('task:create')) scheduleTaskCreatorPrefetch()
})

onBeforeUnmount(() => {
  if (idlePrefetchId !== undefined) window.cancelIdleCallback(idlePrefetchId)
  if (prefetchTimerId !== undefined) window.clearTimeout(prefetchTimerId)
})
</script>

<template>
  <section class="c-series-task-page">
    <header class="c-series-task-page__header">
      <div>
        <p class="c-series-task-page__eyebrow">业务模块</p>
        <h1 class="c-series-task-page__title">{{ title }}</h1>
      </div>
      <div class="c-series-task-page__create-actions">
        <el-button
          v-if="mergeExportUrl && can('task:view')"
          :icon="Download"
          :loading="navigatingUrl === mergeExportUrl"
          :disabled="Boolean(navigatingUrl)"
          @click="openMergeExporter"
        >合并导出</el-button>
        <el-button
          v-if="batchCreateUrl && can('task:create')"
          :icon="DocumentCopy"
          :loading="navigatingUrl === batchCreateUrl"
          :disabled="Boolean(navigatingUrl)"
          @pointerenter="prefetchUrl(batchCreateUrl)"
          @focus="prefetchUrl(batchCreateUrl)"
          @click="openBatchCreator"
        >C31 批量创建</el-button>
        <el-button
          v-if="can('task:create')"
          type="primary"
          :icon="Plus"
          :loading="navigatingUrl === createUrl"
          :disabled="Boolean(navigatingUrl)"
          @pointerenter="prefetchUrl(createUrl)"
          @focus="prefetchUrl(createUrl)"
          @click="openTaskCreator"
        >创建任务</el-button>
      </div>
    </header>

    <section class="c-series-task-page__metrics" aria-label="任务统计">
      <div class="c-series-task-page__metric"><span>任务总数</span><strong>{{ statistics.total_tasks }}</strong></div>
      <div class="c-series-task-page__metric"><span>运行中</span><strong class="is-success">{{ statistics.running_tasks }}</strong></div>
      <div class="c-series-task-page__metric"><span>待执行</span><strong class="is-primary">{{ statistics.pending_tasks }}</strong></div>
      <div class="c-series-task-page__metric"><span>异常任务</span><strong class="is-danger">{{ statistics.error_tasks }}</strong></div>
    </section>

    <section class="c-series-task-page__table-panel">
      <div class="c-series-task-page__toolbar">
        <el-input v-model="filters.keyword" clearable placeholder="搜索任务名称" @keyup.enter="search" />
          <el-select v-model="filters.status" clearable persistent popper-class="c-series-fast-select" placeholder="全部状态">
          <el-option label="待执行" value="pending" />
          <el-option label="运行中" value="running" />
          <el-option label="已完成" value="completed" />
          <el-option label="执行出错" value="error" />
          <el-option label="已取消" value="cancelled" />
        </el-select>
        <div class="c-series-task-page__toolbar-actions">
          <el-button v-if="can('task:restart')" :disabled="selectedTasks.length === 0" @click="batchRestartVisible = true">批量重启<span v-if="selectedTasks.length">（{{ selectedTasks.length }}）</span></el-button>
          <el-button type="primary" @click="search">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
          <el-button text :icon="Refresh" aria-label="刷新任务列表" @click="loadTasks()" />
        </div>
      </div>

      <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" />
      <TaskListTable
        :items="items"
        :loading="loading"
        :can-cancel="can('task:cancel')"
        :can-restart="can('task:restart')"
        :can-delete="can('task:delete')"
        :can-edit="can('task:create')"
        @selection-change="selectedTasks = $event"
        @view="viewTask"
        @cancel="cancelTask"
        @restart="restartTask"
        @restart-fresh="(task) => restartTask(task, false)"
        @create-restart="createRestartTask"
        @edit="viewTask"
        @view-execution="viewTask"
        @remove="removeTask"
      />

      <footer class="c-series-task-page__pagination">
        <span>共 {{ pagination.total }} 条</span>
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.per_page"
          background
          layout="total, sizes, prev, pager, next, jumper"
          :page-sizes="[10, 20, 50]"
          :total="pagination.total"
          @current-change="loadTasks"
          @size-change="() => loadTasks(1)"
        />
      </footer>
    </section>

    <BatchRestartDialog v-model="batchRestartVisible" :tasks="selectedTasks" :submitting="batchRestarting" @submit="restartSelectedTasks" />
  </section>
</template>

<style scoped>
.c-series-task-page { display: grid; gap: 16px; }
.c-series-task-page__header { display: flex; align-items: end; justify-content: space-between; gap: 16px; }
.c-series-task-page__eyebrow { margin: 0 0 2px; color: var(--admin-text-muted); font-size: 13px; }
.c-series-task-page__title { margin: 0; color: var(--admin-text); font-size: 20px; font-weight: 600; line-height: 28px; }
.c-series-task-page__create-actions,
.c-series-task-page__toolbar-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.c-series-task-page__metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }
.c-series-task-page__metric { display: grid; gap: 5px; padding: 16px 20px; border-right: 1px solid var(--admin-border-light); }
.c-series-task-page__metric:last-child { border-right: 0; }
.c-series-task-page__metric span { color: var(--admin-text-muted); font-size: 13px; }
.c-series-task-page__metric strong { color: var(--admin-text); font-size: 24px; font-weight: 600; }
.c-series-task-page__metric .is-success { color: var(--admin-success); }
.c-series-task-page__metric .is-primary { color: var(--admin-primary); }
.c-series-task-page__metric .is-danger { color: var(--admin-danger); }
.c-series-task-page__table-panel { display: grid; gap: 16px; padding: 16px 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }
.c-series-task-page__toolbar { display: flex; flex-wrap: wrap; gap: 10px; }
.c-series-task-page__toolbar :deep(.el-input),
.c-series-task-page__toolbar :deep(.el-select) { width: 210px; }
.c-series-task-page__toolbar-actions { margin-left: auto; }
.c-series-task-page__pagination { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--admin-text-muted); font-size: 13px; }

@media (max-width: 900px) {
  .c-series-task-page__metrics { grid-template-columns: repeat(2, 1fr); }
  .c-series-task-page__metric:nth-child(2) { border-right: 0; }
  .c-series-task-page__metric:nth-child(-n + 2) { border-bottom: 1px solid var(--admin-border-light); }
  .c-series-task-page__toolbar-actions { margin-left: 0; }
  .c-series-task-page__pagination { align-items: start; flex-direction: column; }
  .c-series-task-page__pagination :deep(.el-pagination) { flex-wrap: wrap; }
}

@media (max-width: 560px) {
  .c-series-task-page__header { align-items: start; flex-direction: column; }
  .c-series-task-page__create-actions { width: 100%; }
  .c-series-task-page__metrics { grid-template-columns: 1fr; }
  .c-series-task-page__metric { border-right: 0; border-bottom: 1px solid var(--admin-border-light); }
  .c-series-task-page__metric:last-child { border-bottom: 0; }
  .c-series-task-page__toolbar :deep(.el-input),
  .c-series-task-page__toolbar :deep(.el-select) { width: 100%; }
}
</style>
