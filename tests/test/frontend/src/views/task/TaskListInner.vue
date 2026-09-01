<template>
  <div class="task-list-inner">
    <NPageToolbar eyebrow="TASK QUEUE" :title="`${versionLabel} 任务列表`" description="查看任务排队、执行进度和错误状态，支持版本切换、筛选和移动端快速巡检。">
      <template #actions>
        <n-button v-if="version === 'c3'" size="small" @click="$router.push('/task/create/c31')">
          创建批量任务
        </n-button>
        <n-button type="primary" size="small" @click="$router.push(`/task/create/${version}`)">
          创建新任务
        </n-button>
      </template>
    </NPageToolbar>

    <NStatCardGrid :cards="statCards" :data="stats" />

    <NFilterToolbar v-model="filters" :filters="filterDefs" @search="doFilter" @clear="clearFilters" />

    <!-- Desktop Table -->
    <div v-if="!isMobile" class="task-list-inner__table-wrap">
      <n-spin :show="loading">
        <n-data-table
          :columns="columns"
          :data="tasks"
          :row-key="(row) => row.id"
          :bordered="false"
          :single-line="false"
          size="small"
          striped
        />
      </n-spin>
      <div class="task-list-inner__pagination">
        <span class="task-list-inner__page-info">{{ paginationInfo }}</span>
        <n-pagination
          v-model:page="page"
          v-model:page-size="pageSize"
          :item-count="total"
          :page-sizes="[10, 20, 50]"
          show-size-picker
          @update:page="loadTasks"
          @update:page-size="handlePageSizeChange"
        />
      </div>
    </div>

    <!-- Mobile Cards -->
    <div v-if="isMobile" class="task-list-inner__mobile">
      <n-spin :show="loading">
        <n-empty v-if="!tasks.length && !loading" description="暂无任务" />
        <div v-else class="task-list-inner__cards">
          <div v-for="task in tasks" :key="task.id" class="task-card" @click="router.push(`/task/${task.id}`)">
            <div class="task-card__header">
              <span class="task-card__name">{{ task.name }}</span>
              <NStatusTag :status="task.status" />
            </div>
            <div v-if="task.config?.token_name" class="task-card__meta">
              Token: {{ task.config.token_name }}
            </div>
            <NProgressCell
              v-if="task.total_steps"
              :current-step="task.current_step || 0"
              :total-steps="task.total_steps || 0"
              class="task-card__progress"
            />
            <div class="task-card__footer">
              <span class="task-card__time">{{ formatDateTime(task.start_time || task.created_at) }}</span>
              <n-button
                v-if="task.status === 'running'"
                text
                type="warning"
                size="tiny"
                @click.stop="handleCancel(task.id)"
              >
                停止
              </n-button>
            </div>
          </div>
        </div>
      </n-spin>
      <div class="task-list-inner__pagination">
        <span class="task-list-inner__page-info">{{ paginationInfo }}</span>
        <n-pagination
          v-model:page="page"
          v-model:page-size="pageSize"
          :item-count="total"
          :page-sizes="[10, 20, 50]"
          show-size-picker
          size="small"
          @update:page="loadTasks"
          @update:page-size="handlePageSizeChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage, useDialog, NButton, NTag } from 'naive-ui'
import { getTasks, cancelTask } from '@/api/task'
import NPageToolbar from '@/components/naive/NPageToolbar.vue'
import NStatCardGrid from '@/components/naive/NStatCardGrid.vue'
import NFilterToolbar from '@/components/naive/NFilterToolbar.vue'
import NStatusTag from '@/components/naive/NStatusTag.vue'
import NProgressCell from '@/components/naive/NProgressCell.vue'
import { useResponsive } from '@/composables/useResponsive'
import { usePolling } from '@/composables/usePolling'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const { isMobile } = useResponsive()

const tasks = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const stats = ref({})
const filters = reactive({ status: '', keyword: '' })

const version = computed(() => route.query.version || 'c3')
const versionLabel = computed(() => {
  const labelMap = { c3: 'C3', c4: 'C4', c5: 'C5', c31: 'C31' }
  return labelMap[version.value] || version.value.toUpperCase()
})

const taskTypeMap = { c3: 'google_sheet', c4: 'google_sheet_C4', c5: 'google_sheet_C5', c31: 'google_sheet' }

const statCards = [
  { key: 'total', label: '总任务数', color: '#6366f1' },
  { key: 'completed', label: '已完成', color: '#10b981' },
  { key: 'running', label: '运行中', color: '#f59e0b' },
  { key: 'error', label: '错误', color: '#ef4444' },
]

const filterDefs = [
  {
    key: 'status',
    type: 'select',
    placeholder: '状态筛选',
    options: [
      { value: 'pending', label: '待执行' },
      { value: 'running', label: '运行中' },
      { value: 'completed', label: '已完成' },
      { value: 'cancelled', label: '已取消' },
      { value: 'error', label: '错误' },
    ],
  },
  { key: 'keyword', type: 'input', placeholder: '任务名称 / ID' },
]

const columns = [
  {
    title: '任务名称',
    key: 'name',
    minWidth: 260,
    render(row) {
      return h('div', { class: 'task-cell' }, [
        h('div', { class: 'task-cell__title-row' }, [
          h('a', {
            class: 'task-cell__name',
            onClick: () => router.push(`/task/${row.id}`),
          }, row.name),
          h(NTag, { size: 'tiny', bordered: false, type: 'info' }, () => versionLabel.value),
        ]),
        row.config?.token_name
          ? h('div', { class: 'task-cell__meta' }, `Token: ${row.config.token_name}`)
          : null,
        h('div', { class: 'task-cell__id' }, shortTaskId(row.id)),
      ])
    },
  },
  {
    title: '状态',
    key: 'status',
    width: 90,
    align: 'center',
    render(row) {
      return h(NStatusTag, { status: row.status })
    },
  },
  {
    title: '进度',
    key: 'progress',
    minWidth: 180,
    render(row) {
      return h(NProgressCell, {
        currentStep: row.current_step || 0,
        totalSteps: row.total_steps || 0,
      })
    },
  },
  {
    title: '开始时间',
    key: 'start_time',
    width: 170,
    render(row) {
      return h('span', { class: 'task-cell__time' }, formatDateTime(row.start_time || row.created_at))
    },
  },
  {
    title: '结束时间',
    key: 'end_time',
    width: 170,
    render(row) {
      return h('span', { class: 'task-cell__time' }, formatDateTime(row.end_time))
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 140,
    fixed: 'right',
    align: 'center',
    render(row) {
      const buttons = [
        h(NButton, { text: true, type: 'primary', size: 'small', onClick: () => router.push(`/task/${row.id}`) }, () => '查看'),
      ]
      if (row.status === 'running') {
        buttons.push(
          h(NButton, { text: true, type: 'warning', size: 'small', onClick: () => handleCancel(row.id) }, () => '停止')
        )
      }
      return h('div', { class: 'task-cell__actions' }, buttons)
    },
  },
]

const paginationInfo = computed(() => {
  if (!total.value) return '暂无任务'
  const start = (page.value - 1) * pageSize.value + 1
  const end = Math.min(page.value * pageSize.value, total.value)
  return `${start}-${end} / ${total.value}`
})

async function loadTasks() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value }
    const taskType = taskTypeMap[version.value]
    if (taskType) params.task_type = taskType
    if (filters.status) params.status = filters.status
    if (filters.keyword) params.keyword = filters.keyword

    const res = await getTasks(params)
    tasks.value = res.tasks || []
    total.value = res.pagination?.total || 0

    const currentPageTasks = res.tasks || []
    stats.value = {
      total: res.pagination?.total || 0,
      completed: currentPageTasks.filter((t) => t.status === 'completed').length,
      running: currentPageTasks.filter((t) => t.status === 'running').length,
      error: currentPageTasks.filter((t) => t.status === 'error').length,
    }
  } finally {
    loading.value = false
  }
}

function doFilter() {
  page.value = 1
  loadTasks()
}

function clearFilters() {
  filters.status = ''
  filters.keyword = ''
  doFilter()
}

function handlePageSizeChange() {
  page.value = 1
  loadTasks()
}

function shortTaskId(id) {
  if (!id) return '-'
  return id.length > 8 ? `${id.slice(0, 8)}...` : id
}

function formatDateTime(value) {
  if (!value) return '-'
  const normalized = String(value).replace('T', ' ')
  return normalized.length > 19 ? normalized.slice(0, 19) : normalized
}

function handleCancel(id) {
  dialog.warning({
    title: '确认停止',
    content: '确定要停止这个任务吗？',
    positiveText: '停止',
    negativeText: '取消',
    onPositiveClick: async () => {
      await cancelTask(id)
      message.success('已发送停止请求')
      loadTasks()
    },
  })
}

usePolling(loadTasks, { interval: 30000 })

watch(version, () => {
  page.value = 1
  filters.status = ''
  filters.keyword = ''
  loadTasks()
})
</script>

<style scoped>
.task-list-inner__table-wrap {
  border-radius: 16px;
  background: #111827;
  border: 1px solid rgba(148, 163, 184, 0.1);
  padding: 4px;
  overflow: hidden;
}

.task-list-inner__pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-top: 1px solid rgba(148, 163, 184, 0.08);
}

.task-list-inner__page-info {
  font-size: 12px;
  color: #64748b;
  font-family: 'JetBrains Mono', monospace;
}

.task-cell {
  padding: 4px 0;
}

.task-cell__title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.task-cell__name {
  font-size: 14px;
  font-weight: 600;
  color: #c7d2fe;
  cursor: pointer;
  transition: color 0.15s;
}

.task-cell__name:hover {
  color: #a5b4fc;
  text-decoration: underline;
}

.task-cell__meta {
  margin-top: 3px;
  font-size: 12px;
  color: #64748b;
}

.task-cell__id {
  margin-top: 2px;
  font-size: 11px;
  color: #475569;
  font-family: 'JetBrains Mono', monospace;
}

.task-cell__time {
  font-size: 13px;
  color: #94a3b8;
  font-family: 'JetBrains Mono', monospace;
}

.task-cell__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.task-list-inner__mobile {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-list-inner__cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.task-card {
  padding: 14px 16px;
  border-radius: 12px;
  background: #111827;
  border: 1px solid rgba(148, 163, 184, 0.1);
  cursor: pointer;
  transition: border-color 0.2s;
}

.task-card:active {
  border-color: rgba(99, 102, 241, 0.4);
}

.task-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.task-card__name {
  font-size: 14px;
  font-weight: 600;
  color: #c7d2fe;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.task-card__meta {
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
}

.task-card__progress {
  margin-top: 10px;
}

.task-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}

.task-card__time {
  font-size: 12px;
  color: #475569;
  font-family: 'JetBrains Mono', monospace;
}
</style>
