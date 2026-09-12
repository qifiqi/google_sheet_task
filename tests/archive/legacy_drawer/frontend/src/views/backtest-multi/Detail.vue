<template>
  <div class="app-page backtest-multi-detail-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Multi-Product Monitor</div>
        <h2 class="page-title">多产品回测详情</h2>
        <p class="page-description">查看多产品回测任务执行状态、日志和结果。</p>
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
        <el-button class="page-back-button" @click="$router.push('/backtest-multi/list')">返回列表</el-button>
      </div>
    </div>

    <div v-loading="loading">
      <el-row v-if="task" :gutter="16" class="backtest-multi-detail-page__metrics">
        <el-col :xs="24" :md="8">
          <el-card shadow="never" class="page-section">
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
                <TaskProgressCell :current-step="task.current_step || 0" :total-steps="task.total_steps || 0" />
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>

        <el-col :xs="24" :md="8">
          <el-card shadow="never" class="page-section">
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

        <el-col :xs="24" :md="8">
          <div class="hero-panel">
            <div class="hero-panel__eyebrow">Execution Summary</div>
            <div class="backtest-multi-detail-page__hero-stats">
              <div class="backtest-multi-detail-page__hero-stat">
                <div class="backtest-multi-detail-page__hero-value">{{ summary.success_count ?? 0 }}</div>
                <div class="backtest-multi-detail-page__hero-label">成功</div>
              </div>
              <div class="backtest-multi-detail-page__hero-stat">
                <div class="backtest-multi-detail-page__hero-value">{{ summary.failed_count ?? 0 }}</div>
                <div class="backtest-multi-detail-page__hero-label">失败</div>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>

      <div v-if="task" class="page-section">
        <div class="action-bar">
          <el-button @click="$router.push(`/backtest-multi/${taskId}/global-preview`)">全局预览页</el-button>
          <el-button @click="$router.push(`/backtest-multi/${taskId}/result`)">回测结果</el-button>
        </div>
      </div>

      <el-card v-if="task" shadow="never" class="page-section">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="任务日志" name="logs">
            <div ref="logContainerRef" class="backtest-multi-detail-page__log-panel">
              <div v-if="!logs.length" class="panel-note panel-note--center">暂无日志</div>
              <div v-for="(log, index) in logs" :key="index" :class="['log-line', `log-${log.level}`]">
                [{{ log.timestamp }}] [{{ (log.level || 'info').toUpperCase() }}] {{ log.message }}
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="执行结果" name="results">
            <el-table :data="results" stripe>
              <el-table-column prop="id" label="结果 ID" min-width="180">
                <template #default="{ row }">
                  <span class="font-mono">{{ row.id }}</span>
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
                  <el-button link type="primary" @click="viewResult(row)">查看</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div class="backtest-multi-detail-page__pagination">
              <el-pagination
                v-model:current-page="resultPage"
                v-model:page-size="resultPageSize"
                :total="resultTotal"
                layout="total, prev, pager, next"
                @current-change="loadResults"
              />
            </div>
          </el-tab-pane>

          <el-tab-pane label="任务配置" name="config">
            <pre class="code-block">{{ JSON.stringify(task.config || {}, null, 2) }}</pre>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </div>

    <el-drawer v-model="resultDrawerVisible" title="结果详情" :size="isMobile ? '100%' : '560px'">
      <div v-if="currentResult">
        <div class="backtest-multi-detail-page__drawer-section">
          <div class="backtest-multi-detail-page__card-title">参数信息</div>
          <pre class="code-block">{{ JSON.stringify(currentResult.parameters, null, 2) }}</pre>
        </div>
        <div class="backtest-multi-detail-page__drawer-section">
          <div class="backtest-multi-detail-page__card-title">执行结果</div>
          <pre class="code-block">{{ JSON.stringify(currentResult.result, null, 2) }}</pre>
        </div>
        <div v-if="currentResult.error_message" class="backtest-multi-detail-page__drawer-section">
          <div class="backtest-multi-detail-page__card-title">错误信息</div>
          <pre class="backtest-multi-detail-page__error-block">{{ currentResult.error_message }}</pre>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { getTaskResults } from '@/api/backtestMulti'
import {
  getTask,
  getTaskLogs,
  cancelTask,
  restartTask,
  checkTaskStatus as apiCheckStatus
} from '@/api/task'
import StatusTag from '@/components/StatusTag.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'
import { useResponsive } from '@/composables/useResponsive'

const route = useRoute()
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
let pollTimer = null

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
  try {
    const res = await getTaskResults(taskId, { page: resultPage.value, per_page: resultPageSize.value })
    results.value = res.results || []
    resultTotal.value = res.total || res.pagination?.total || 0
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
.backtest-multi-detail-page__metrics {
  margin-bottom: 16px;
}

.backtest-multi-detail-page__hero-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.backtest-multi-detail-page__hero-stat {
  padding: 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.08);
  text-align: center;
}

.backtest-multi-detail-page__hero-value {
  color: #fff;
  font-size: 28px;
  font-weight: 700;
}

.backtest-multi-detail-page__hero-label {
  color: rgba(255, 255, 255, 0.76);
  font-size: 12px;
}

.backtest-multi-detail-page__log-panel {
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

.backtest-multi-detail-page__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.backtest-multi-detail-page__drawer-section {
  display: grid;
  gap: 8px;
  margin-bottom: 16px;
}

.backtest-multi-detail-page__card-title {
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
}

.backtest-multi-detail-page__error-block {
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

.log-info { color: #93c5fd; }
.log-warning { color: #fcd34d; }
.log-error { color: #fca5a5; }
</style>
