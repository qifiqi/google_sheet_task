<template>
  <div class="app-page merge-export-page">
    <PageToolbar
      eyebrow="Google Sheet"
      title="C3 合并导出"
      description="搜索并选择多个 C3 任务，合并导出 Excel 文件。"
    >
      <template #actions>
        <el-button class="page-back-button" @click="$router.push('/task/list?version=c3')">返回列表</el-button>
      </template>
    </PageToolbar>

    <FilterToolbar
      v-model="filters"
      :filters="filterDefs"
      @search="doSearch"
      @clear="resetSearch"
    />

    <el-card shadow="never" class="merge-export-page__actions-card">
      <div class="merge-export-page__actions">
        <div class="merge-export-page__selection">
          <span>已选 <el-tag :type="overLimit ? 'danger' : 'primary'" size="small">{{ selectedIds.size }}</el-tag> 个任务</span>
          <el-button-group size="small">
            <el-button @click="selectAllPage">全选当页</el-button>
            <el-button @click="deselectAll">清空选择</el-button>
            <el-button @click="invertSelection">反选</el-button>
          </el-button-group>
        </div>
        <div class="merge-export-page__export">
          <el-button
            type="success"
            :disabled="selectedIds.size === 0 || overLimit || exporting"
            :loading="exporting"
            @click="doExport"
          >
            导出选中任务
          </el-button>
          <span class="merge-export-page__hint">最多 10 个任务</span>
        </div>
      </div>
      <el-progress
        v-if="exporting || progressVisible"
        :percentage="progressPercent >= 0 ? progressPercent : 100"
        :indeterminate="progressPercent < 0"
        :stroke-width="6"
        class="merge-export-page__progress"
      />
      <div v-if="progressText" class="merge-export-page__progress-text">{{ progressText }}</div>
    </el-card>

    <DataTableCard
      :data="tasks"
      :loading="loading"
      :total="total"
      v-model:page="page"
      v-model:page-size="pageSize"
      :page-sizes="[10, 20, 50, 100]"
      @page-change="loadTasks"
    >
      <el-table-column width="46" align="center">
        <template #header>
          <el-checkbox
            :model-value="headerChecked"
            :indeterminate="headerIndeterminate"
            @change="toggleAllPage"
          />
        </template>
        <template #default="{ row }">
          <el-checkbox
            :model-value="selectedIds.has(row.id)"
            @change="toggleRow(row)"
          />
        </template>
      </el-table-column>
      <el-table-column label="ID" width="110" sortable prop="id">
        <template #default="{ row }">
          <span class="font-mono inline-muted">{{ row.id?.slice(0, 8) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="任务名称" min-width="200" sortable prop="name">
        <template #default="{ row }">
          <div>{{ row.name }}</div>
          <div v-if="row.description" class="inline-muted merge-export-page__desc">{{ row.description }}</div>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="160" sortable prop="created_at">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100" sortable prop="status">
        <template #default="{ row }">
          <StatusTag :status="row.status" />
        </template>
      </el-table-column>
      <el-table-column label="进度" width="120">
        <template #default="{ row }">
          <TaskProgressCell :current-step="row.current_step || 0" :total-steps="row.total_steps || 0" />
        </template>
      </el-table-column>
      <el-table-column label="开始时间" width="160">
        <template #default="{ row }">{{ formatDateTime(row.start_time) }}</template>
      </el-table-column>
      <el-table-column label="结束时间" width="160">
        <template #default="{ row }">{{ formatDateTime(row.end_time) }}</template>
      </el-table-column>
    </DataTableCard>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getTasks, exportTasksBatchStream } from '@/api/task'
import { formatDateTime } from '@/utils/format'
import PageToolbar from '@/components/PageToolbar.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import DataTableCard from '@/components/DataTableCard.vue'
import StatusTag from '@/components/StatusTag.vue'
import TaskProgressCell from '@/components/TaskProgressCell.vue'

const MAX_EXPORT_TASKS = 10

const tasks = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const filters = reactive({ keyword: '', status: '' })
const selectedIds = reactive(new Set())

const exporting = ref(false)
const progressVisible = ref(false)
const progressPercent = ref(0)
const progressText = ref('')

const filterDefs = [
  { key: 'keyword', type: 'input', placeholder: '输入任务名称关键词搜索…', span: { xs: 24, sm: 10 } },
  { key: 'status', type: 'select', placeholder: '全部状态', span: { xs: 24, sm: 6 }, options: [
    { value: 'completed', label: '已完成' },
    { value: 'running', label: '执行中' },
    { value: 'error', label: '执行出错' },
    { value: 'cancelled', label: '已取消' },
  ]},
]

const overLimit = computed(() => selectedIds.size > MAX_EXPORT_TASKS)
const headerChecked = computed(() =>
  tasks.value.length > 0 && tasks.value.every((t) => selectedIds.has(t.id))
)
const headerIndeterminate = computed(() =>
  !headerChecked.value && tasks.value.some((t) => selectedIds.has(t.id))
)

async function loadTasks() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value, task_type: 'google_sheet' }
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.status) params.status = filters.status
    const res = await getTasks(params)
    tasks.value = res.items || []
    total.value = res.total || 0
  } catch (error) {
    ElMessage.error(error.message || '搜索失败')
  } finally {
    loading.value = false
  }
}

function doSearch() {
  page.value = 1
  loadTasks()
}

function resetSearch() {
  filters.keyword = ''
  filters.status = ''
  doSearch()
}

function toggleRow(task) {
  const id = task.id
  if (selectedIds.has(id)) {
    selectedIds.delete(id)
  } else {
    selectedIds.add(id)
  }
}

function toggleAllPage(checked) {
  tasks.value.forEach((t) => {
    if (checked) {
      selectedIds.add(t.id)
    } else {
      selectedIds.delete(t.id)
    }
  })
}

function selectAllPage() {
  tasks.value.forEach((t) => selectedIds.add(t.id))
}

function deselectAll() {
  selectedIds.clear()
}

function invertSelection() {
  tasks.value.forEach((t) => {
    if (selectedIds.has(t.id)) {
      selectedIds.delete(t.id)
    } else {
      selectedIds.add(t.id)
    }
  })
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

async function doExport() {
  const ids = Array.from(selectedIds)
  if (!ids.length) return
  if (ids.length > MAX_EXPORT_TASKS) {
    ElMessage.warning(`合并导出最多支持 ${MAX_EXPORT_TASKS} 个任务，当前已选 ${ids.length} 个`)
    return
  }

  exporting.value = true
  progressVisible.value = true
  progressPercent.value = 0
  progressText.value = '正在生成文件，请稍候…'

  try {
    const { blob, filename } = await exportTasksBatchStream(ids, {
      onProgress(info) {
        if (info.percent < 0) {
          progressPercent.value = -1
          progressText.value = `下载中… ${formatBytes(info.received)}`
        } else {
          progressPercent.value = info.percent
          progressText.value = `下载中… ${formatBytes(info.received)} / ${formatBytes(info.total)}`
        }
      },
    })
    triggerDownload(blob, filename)
    progressPercent.value = 100
    progressText.value = '下载完成'
    ElMessage.success(`合并导出成功（${ids.length} 个任务）`)
    setTimeout(() => {
      progressVisible.value = false
      progressText.value = ''
    }, 2000)
  } catch (error) {
    progressVisible.value = false
    progressText.value = ''
    ElMessage.error(error.message || '合并导出失败')
  } finally {
    exporting.value = false
  }
}

onMounted(loadTasks)
</script>

<style scoped>
.merge-export-page__actions-card {
  margin-bottom: 16px;
}

.merge-export-page__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.merge-export-page__selection {
  display: flex;
  align-items: center;
  gap: 12px;
}

.merge-export-page__export {
  display: flex;
  align-items: center;
  gap: 8px;
}

.merge-export-page__hint {
  font-size: var(--app-font-xs, 12px);
  color: var(--app-text-muted, #909399);
}

.merge-export-page__progress {
  margin-top: 12px;
}

.merge-export-page__progress-text {
  margin-top: 4px;
  font-size: var(--app-font-xs, 12px);
  color: var(--app-text-muted, #909399);
}

.merge-export-page__desc {
  font-size: var(--app-font-xs, 12px);
}
</style>
