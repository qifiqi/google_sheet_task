<template>
  <div class="task-detail-page" v-loading="loading">
    <PageToolbar eyebrow="任务详情" :title="task?.task_name || `任务 #${taskId}`">
      <template #actions>
        <TaskActions v-if="task" :task="task" @refresh="loadTask" />
      </template>
    </PageToolbar>

    <template v-if="task">
      <StatCardGrid
        :cards="DETAIL_CARDS"
        :data="detailStats"
        :columns="{ xs: 12, sm: 6, md: 6 }"
        class="mb-4"
      />

      <el-tabs v-model="activeTab" class="task-detail-tabs">
        <!-- Logs Tab -->
        <el-tab-pane label="执行日志" name="logs">
          <div class="tab-toolbar mb-3">
            <el-button size="small" @click="loadLogs">
              <el-icon><Refresh /></el-icon> 刷新
            </el-button>
            <el-switch v-model="autoScroll" active-text="自动滚动" size="small" />
          </div>
          <LogViewer :logs="logs" :auto-scroll="autoScroll" />
        </el-tab-pane>

        <!-- Results Tab -->
        <el-tab-pane label="执行结果" name="results">
          <el-table :data="results" stripe style="width: 100%">
            <el-table-column prop="parameter_index" label="参数序号" width="100" />
            <el-table-column label="状态" width="100" align="center">
              <template #default="{ row }">
                <StatusTag :status="row.status" />
              </template>
            </el-table-column>
            <el-table-column prop="result_data" label="结果" min-width="200" show-overflow-tooltip />
            <el-table-column prop="created_at" label="时间" width="170">
              <template #default="{ row }"><span class="cell-time">{{ formatTime(row.created_at) }}</span></template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- Config Tab -->
        <el-tab-pane label="任务配置" name="config">
          <CodeBlock :code="JSON.stringify(task.config || {}, null, 2)" language="json" />
        </el-tab-pane>

        <!-- Error Tab -->
        <el-tab-pane v-if="task.error_message" label="错误信息" name="error">
          <el-alert
            :title="task.error_message"
            type="error"
            :closable="false"
            show-icon
          />
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import { getTask, getTaskLogs, getTaskResults } from '@/api/task'
import PageToolbar from '@/components/PageToolbar.vue'
import StatCardGrid from '@/components/StatCardGrid.vue'
import StatusTag from '@/components/StatusTag.vue'
import LogViewer from '@/components/LogViewer.vue'
import CodeBlock from '@/components/CodeBlock.vue'
import TaskActions from './components/TaskActions.vue'

const route = useRoute()
const taskId = computed(() => route.params.id)

const task = ref(null)
const logs = ref([])
const results = ref([])
const loading = ref(false)
const activeTab = ref('logs')
const autoScroll = ref(true)
let pollTimer = null

const DETAIL_CARDS = [
  { key: 'status', label: '当前状态' },
  { key: 'progress', label: '执行进度' },
  { key: 'task_type', label: '任务类型' },
  { key: 'elapsed', label: '运行时长' },
]

const detailStats = computed(() => {
  if (!task.value) return {}
  const t = task.value
  return {
    status: t.status || '-',
    progress: `${t.current_step || 0} / ${t.total_steps || 0}`,
    task_type: t.task_type || '-',
    elapsed: calcElapsed(t.start_time, t.end_time),
  }
})

function formatTime(str) {
  if (!str) return '-'
  return new Date(str).toLocaleString('zh-CN')
}

function calcElapsed(start, end) {
  if (!start) return '-'
  const s = new Date(start)
  const e = end ? new Date(end) : new Date()
  const diff = Math.floor((e - s) / 1000)
  if (diff < 60) return `${diff}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ${diff % 60}s`
  return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`
}

async function loadTask() {
  loading.value = true
  try {
    const res = await getTask(taskId.value)
    task.value = res.data || res
  } catch {
    task.value = null
  } finally {
    loading.value = false
  }
}

async function loadLogs() {
  try {
    const res = await getTaskLogs(taskId.value)
    logs.value = Array.isArray(res) ? res : (res.data || [])
  } catch { logs.value = [] }
}

async function loadResults() {
  try {
    const res = await getTaskResults(taskId.value)
    results.value = Array.isArray(res) ? res : (res.data || res.results || [])
  } catch { results.value = [] }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    if (task.value?.status === 'running' || task.value?.status === 'pending') {
      loadTask()
      loadLogs()
    }
  }, 5000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(async () => {
  await loadTask()
  await Promise.all([loadLogs(), loadResults()])
  startPolling()
})

onBeforeUnmount(stopPolling)
</script>

<style lang="scss" scoped>
.tab-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.task-detail-tabs {
  margin-top: 8px;
}

.cell-time {
  font-size: var(--app-font-sm);
  color: var(--app-text-muted);
  white-space: nowrap;
}
</style>
