<script setup lang="ts">
import { computed, onMounted, reactive, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, ArrowLeft, Download, EditPen, Refresh, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ResultDetailDialog from '../tasks/ResultDetailDialog.vue'
import TaskEditDialog from '../tasks/TaskEditDialog.vue'
import SystemLogViewer from '../system/SystemLogViewer.vue'
import CSeriesResultTable from './CSeriesResultTable.vue'
import CSeriesTaskConfigOverview from './CSeriesTaskConfigOverview.vue'
import CSeriesTaskOverview from './CSeriesTaskOverview.vue'
import { requestJson } from '../../api/http'
import { useAuthStore } from '../../stores/auth'
import { downloadFile } from '../../utils/download'
import { formatDateTime } from '../../utils/format'
import type { TaskItem, TaskLogItem, TaskResultDetail, TaskResultItem } from '../../types/api'
import type { SystemLogEntry } from '../../types/system'

const props = defineProps<{
  listRoute: 'C3Tasks' | 'C4Tasks' | 'C5Tasks' | 'C7Tasks'
  createRoute: 'C3TaskCreate' | 'C4TaskCreate' | 'C5TaskCreate' | 'C7TaskCreate'
  mode: 'c3' | 'c4' | 'c5' | 'c7'
}>()

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const task = shallowRef<TaskItem | null>(null)
const taskLogs = shallowRef<TaskLogItem[]>([])
const resultItems = shallowRef<TaskResultItem[]>([])
const loading = shallowRef(false)
const logsLoading = shallowRef(false)
const resultsLoading = shallowRef(false)
const exporting = shallowRef(false)
const savingTask = shallowRef(false)
const editVisible = shallowRef(false)
const resultDetailVisible = shallowRef(false)
const selectedResult = shallowRef<TaskResultDetail | null>(null)
const selectedModelKey = shallowRef<string | null>(null)
const errorMessage = shallowRef('')
const resultsError = shallowRef('')
type DetailSection = 'config' | 'results' | 'logs'
const expandedSections = shallowRef<DetailSection[]>(['config', 'results', 'logs'])
const taskId = computed(() => String(route.params.taskId || ''))
const pagination = reactive({ page: 1, perPage: 10, total: 0, pages: 0, totalSuccess: 0, totalFailed: 0 })
const config = computed<Record<string, unknown>>(() => task.value?.config || {})
const isRunning = computed(() => task.value?.status === 'running')
const taskLogEntries = computed<SystemLogEntry[]>(() => taskLogs.value.map((log) => ({ timestamp: log.timestamp || '', level: String(log.level || 'info'), source: log.source || 'task', message: log.message })))

function can(permission: string) { return auth.hasPermission(permission) }
function isSectionExpanded(section: DetailSection) { return expandedSections.value.includes(section) }
function toggleSection(section: DetailSection) {
  expandedSections.value = isSectionExpanded(section)
    ? expandedSections.value.filter((item) => item !== section)
    : [...expandedSections.value, section]
}

async function loadResults(page = pagination.page) {
  if (!taskId.value) return
  resultsLoading.value = true
  resultsError.value = ''
  try {
    const data = await requestJson<{ results: TaskResultItem[]; total: number; pages: number; current_page: number; total_success?: number; total_failed?: number }>(`/api/tasks/${encodeURIComponent(taskId.value)}/results?page=${page}&per_page=${pagination.perPage}&compact=1`)
    resultItems.value = data.results || []
    Object.assign(pagination, { page: data.current_page || page, total: data.total || 0, pages: data.pages || 0, totalSuccess: data.total_success || 0, totalFailed: data.total_failed || 0 })
  } catch (error) {
    resultsError.value = error instanceof Error ? error.message : '加载任务结果失败'
  } finally {
    resultsLoading.value = false
  }
}

async function loadTask() {
  if (!taskId.value) return
  loading.value = true
  logsLoading.value = true
  errorMessage.value = ''
  try {
    void loadResults(1)
    const [taskResponse, logsResponse] = await Promise.all([
      requestJson<{ task: TaskItem }>(`/api/tasks/${encodeURIComponent(taskId.value)}`),
      requestJson<{ logs: TaskLogItem[] }>(`/api/tasks/${encodeURIComponent(taskId.value)}/logs`),
    ])
    task.value = taskResponse.task
    taskLogs.value = logsResponse.logs || []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '加载任务详情失败'
  } finally {
    loading.value = false
    logsLoading.value = false
  }
}

function returnToList() { void router.push({ name: props.listRoute }) }
function restartFromConfig() { if (task.value) void router.push({ name: props.createRoute, query: { restart_task_id: task.value.id } }) }

async function checkStatus() {
  if (!task.value) return
  try {
    const data = await requestJson<{ status_check: { db_status?: string; memory_running?: boolean; current_step?: number; total_steps?: number; latest_log_time?: string; can_restart?: boolean; restart_reason?: string } }>(`/api/tasks/${encodeURIComponent(task.value.id)}/status-check`)
    const check = data.status_check
    const message = [`数据库状态：${check.db_status || '-'}`, `内存状态：${check.memory_running ? '运行中' : '未运行'}`, `执行进度：${check.current_step || 0} / ${check.total_steps || 0}`, check.latest_log_time ? `最新日志：${formatDateTime(check.latest_log_time)}` : '', check.can_restart ? `建议重启：${check.restart_reason || '检测到异常'}` : '状态检查正常'].filter(Boolean).join('\n')
    await ElMessageBox.alert(message, '任务状态检查', { confirmButtonText: '知道了' })
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '状态检查失败') }
}

async function cancelTask() {
  if (!task.value) return
  try {
    await ElMessageBox.confirm(`确定停止“${task.value.name}”吗？`, '停止任务', { type: 'warning', confirmButtonText: '停止' })
    await requestJson(`/api/tasks/${encodeURIComponent(task.value.id)}/cancel`, { method: 'POST' })
    ElMessage.success('已发送停止请求')
    await loadTask()
  } catch (error) { if (error !== 'cancel') ElMessage.error(error instanceof Error ? error.message : '停止任务失败') }
}

async function restartTask(resumeFromCheckpoint: boolean) {
  if (!task.value) return
  const label = resumeFromCheckpoint ? '从断点重启' : '从头重启'
  try {
    await ElMessageBox.confirm(`确定${label}“${task.value.name}”吗？`, '重启任务', { type: 'warning', confirmButtonText: '重启' })
    await requestJson(`/api/tasks/${encodeURIComponent(task.value.id)}/restart`, { method: 'POST', body: JSON.stringify({ resume_from_checkpoint: resumeFromCheckpoint }) })
    ElMessage.success(`已提交${label}`)
    await loadTask()
  } catch (error) { if (error !== 'cancel') ElMessage.error(error instanceof Error ? error.message : `${label}失败`) }
}

function handleRestartCommand(command: string) { void restartTask(command === 'resume') }

async function saveTaskEdit(payload: { id: string; name: string; description: string; status: string; config: Record<string, unknown> }) {
  savingTask.value = true
  try {
    await requestJson(`/api/tasks/${encodeURIComponent(payload.id)}/config`, { method: 'PUT', body: JSON.stringify(payload) })
    editVisible.value = false
    ElMessage.success('任务配置已更新')
    await loadTask()
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : '更新任务配置失败') } finally { savingTask.value = false }
}

async function openResult(result: TaskResultItem, modelKey: string) {
  resultDetailVisible.value = true
  selectedResult.value = null
  selectedModelKey.value = modelKey
  try { selectedResult.value = await requestJson<TaskResultDetail>(`/api/results/${result.id}`) } catch (error) { ElMessage.error(error instanceof Error ? error.message : '加载结果详情失败') }
}

async function exportResults() {
  if (!task.value) return
  exporting.value = true
  try { await downloadFile(`/api/tasks/${encodeURIComponent(task.value.id)}/export`, `${task.value.name}-results.xlsx`) } catch (error) { ElMessage.error(error instanceof Error ? error.message : '导出任务结果失败') } finally { exporting.value = false }
}

watch(taskId, () => { void loadTask() })
onMounted(() => { void loadTask() })
</script>

<template>
  <section class="c-series-task-detail">
    <header class="c-series-task-detail__header">
      <div><p>业务模块 / Google Sheet</p><h1>{{ task?.name || '任务详情' }}</h1></div>
      <div class="c-series-task-detail__header-actions"><el-button :icon="Refresh" :loading="loading" @click="loadTask">刷新</el-button><el-button :icon="VideoPlay" @click="checkStatus">检查状态</el-button><el-button :icon="ArrowLeft" @click="returnToList">返回任务列表</el-button></div>
    </header>
    <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" />
    <template v-else-if="task">
      <CSeriesTaskOverview :task="task" :total-success="pagination.totalSuccess" :total-failed="pagination.totalFailed" />
      <section class="c-series-task-detail__panel">
        <header class="c-series-task-detail__panel-header">
          <div
            class="c-series-task-detail__section-toggle"
            role="button"
            tabindex="0"
            :aria-label="isSectionExpanded('config') ? '折叠任务配置' : '展开任务配置'"
            :aria-expanded="isSectionExpanded('config')"
            aria-controls="task-config-content"
            @click="toggleSection('config')"
            @keydown.enter.prevent="toggleSection('config')"
            @keydown.space.prevent="toggleSection('config')"
          ><h2>任务配置</h2><p>优先展示会影响执行和结果的字段；认证与行情细节按需展开。</p></div>
          <div class="c-series-task-detail__actions">
            <el-button v-if="can('task:create') && !isRunning" :icon="EditPen" @click="editVisible = true">编辑配置</el-button>
            <el-dropdown v-if="can('task:restart') && !isRunning" trigger="click" @command="handleRestartCommand">
              <el-button type="primary">立即重启<el-icon class="c-series-task-detail__restart-arrow"><ArrowDown /></el-icon></el-button>
              <template #dropdown><el-dropdown-menu><el-dropdown-item command="resume">从断点重启</el-dropdown-item><el-dropdown-item command="fresh">从头重启</el-dropdown-item></el-dropdown-menu></template>
            </el-dropdown>
            <el-button v-if="can('task:restart') && !isRunning" @click="restartFromConfig">基于配置新建</el-button>
            <el-button v-if="can('task:cancel') && isRunning" type="warning" @click="cancelTask">停止任务</el-button>
          </div>
        </header>
        <el-collapse-transition>
          <div v-show="isSectionExpanded('config')" id="task-config-content" class="c-series-task-detail__panel-content">
            <CSeriesTaskConfigOverview :config="config" :mode="mode" />
          </div>
        </el-collapse-transition>
      </section>
      <section class="c-series-task-detail__panel">
        <header class="c-series-task-detail__panel-header">
          <div
            class="c-series-task-detail__section-toggle"
            role="button"
            tabindex="0"
            :aria-label="isSectionExpanded('results') ? '折叠任务结果' : '展开任务结果'"
            :aria-expanded="isSectionExpanded('results')"
            aria-controls="task-results-content"
            @click="toggleSection('results')"
            @keydown.enter.prevent="toggleSection('results')"
            @keydown.space.prevent="toggleSection('results')"
          ><h2>任务结果</h2><p>一组记录对应一次参数执行；同组模型保持在同一行对比。</p></div>
          <div class="c-series-task-detail__actions">
            <el-button :icon="Download" :loading="exporting" @click="exportResults">导出结果</el-button>
          </div>
        </header>
        <el-collapse-transition>
          <div v-show="isSectionExpanded('results')" id="task-results-content" class="c-series-task-detail__panel-content">
            <el-alert v-if="resultsError" :title="resultsError" type="error" show-icon :closable="false" />
            <CSeriesResultTable :items="resultItems" :loading="resultsLoading" @view="openResult" />
            <footer class="c-series-task-detail__pagination"><span>共 {{ pagination.total }} 个参数组合，成功 {{ pagination.totalSuccess }} 个，失败 {{ pagination.totalFailed }} 个</span><el-pagination v-model:current-page="pagination.page" v-model:page-size="pagination.perPage" background layout="total, sizes, prev, pager, next" :page-sizes="[10, 20, 50]" :total="pagination.total" @current-change="loadResults" @size-change="() => loadResults(1)" /></footer>
          </div>
        </el-collapse-transition>
      </section>
      <section class="c-series-task-detail__panel">
        <header class="c-series-task-detail__panel-header">
          <div
            class="c-series-task-detail__section-toggle"
            role="button"
            tabindex="0"
            :aria-label="isSectionExpanded('logs') ? '折叠任务日志' : '展开任务日志'"
            :aria-expanded="isSectionExpanded('logs')"
            aria-controls="task-logs-content"
            @click="toggleSection('logs')"
            @keydown.enter.prevent="toggleSection('logs')"
            @keydown.space.prevent="toggleSection('logs')"
          ><h2>任务运行日志</h2><p>记录当前任务的执行阶段与异常信息。</p></div>
        </header>
        <el-collapse-transition>
          <div v-show="isSectionExpanded('logs')" id="task-logs-content" class="c-series-task-detail__panel-content">
            <SystemLogViewer title="任务运行日志" empty-description="暂无任务日志" height="420px" follow-tail :logs="taskLogEntries" :loading="logsLoading" />
          </div>
        </el-collapse-transition>
      </section>
    </template>
    <section v-else-if="!loading" class="c-series-task-detail__empty"><el-empty description="未找到任务" /></section>
    <TaskEditDialog v-model="editVisible" :task="task" :submitting="savingTask" @save="saveTaskEdit" />
    <ResultDetailDialog v-model="resultDetailVisible" :result="selectedResult" :model-key="selectedModelKey" />
  </section>
</template>

<style scoped>
.c-series-task-detail { display: grid; max-width: 1440px; gap: 16px; margin: 0 auto; }.c-series-task-detail__header, .c-series-task-detail__header-actions, .c-series-task-detail__panel-header, .c-series-task-detail__actions { display: flex; align-items: end; justify-content: space-between; gap: 12px; }.c-series-task-detail__header p, .c-series-task-detail__panel p { margin: 0; color: var(--admin-text-muted); font-size: 13px; }.c-series-task-detail__header h1, .c-series-task-detail__panel h2 { margin: 2px 0 0; color: var(--admin-text); font-weight: 600; }.c-series-task-detail__header h1 { font-size: 20px; line-height: 28px; }.c-series-task-detail__panel h2 { font-size: 16px; line-height: 24px; }.c-series-task-detail__panel p { margin-top: 3px; }.c-series-task-detail__panel, .c-series-task-detail__empty { display: grid; gap: 16px; padding: 20px; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-surface); }.c-series-task-detail__panel-content { display: grid; gap: 16px; min-width: 0; }.c-series-task-detail__section-toggle { min-width: 0; border-radius: 4px; cursor: pointer; }.c-series-task-detail__section-toggle:hover h2 { color: var(--el-color-primary); }.c-series-task-detail__section-toggle:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 3px; }.c-series-task-detail__actions { flex-wrap: wrap; justify-content: end; }.c-series-task-detail__restart-arrow { margin-left: 4px; }.c-series-task-detail__pagination { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--admin-text-muted); font-size: 13px; }
@media (max-width: 760px) { .c-series-task-detail__header, .c-series-task-detail__panel-header { align-items: stretch; flex-direction: column; }.c-series-task-detail__header-actions { display: grid; grid-template-columns: 1fr 1fr; }.c-series-task-detail__header-actions :deep(.el-button:last-child) { grid-column: 1 / -1; }.c-series-task-detail__pagination { align-items: start; flex-direction: column; }.c-series-task-detail__pagination :deep(.el-pagination) { flex-wrap: wrap; } }
@media (max-width: 640px) { .c-series-task-detail__panel, .c-series-task-detail__empty { padding: 16px; }.c-series-task-detail__actions { display: grid; grid-template-columns: 1fr; }.c-series-task-detail__actions :deep(.el-button) { margin: 0; } }
</style>
