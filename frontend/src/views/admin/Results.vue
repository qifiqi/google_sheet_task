<template>
  <div class="admin-results">
    <PageToolbar eyebrow="管理中心" title="结果查询" description="查看任务执行结果" />

    <FilterToolbar
      :filters="FILTERS"
      v-model="filterValues"
      @search="loadResults"
      @clear="clearFilters"
      class="mb-3"
    />

    <el-table :data="results" v-loading="loading" stripe style="width: 100%">
      <el-table-column prop="task_id" label="任务 ID" width="90" />
      <el-table-column prop="template_name" label="模板" min-width="140" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'success' ? 'success' : row.status === 'error' ? 'danger' : 'info'" size="small">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="170">
        <template #default="{ row }"><span class="cell-time">{{ formatTime(row.created_at) }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right" align="center">
        <template #default="{ row }">
          <el-button type="primary" size="small" text @click.stop="viewResult(row)">查看</el-button>
          <el-popconfirm title="确定删除此结果？" @confirm="handleDelete(row)">
            <template #reference>
              <el-button type="danger" size="small" text @click.stop>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadResults"
        @current-change="loadResults"
      />
    </div>

    <!-- JSON Viewer Dialog -->
    <el-dialog v-model="viewerVisible" title="结果详情" width="750px" destroy-on-close>
      <div v-if="selectedResult" class="result-detail">
        <el-descriptions :column="2" border class="mb-4">
          <el-descriptions-item label="ID">{{ selectedResult.id }}</el-descriptions-item>
          <el-descriptions-item label="任务 ID">{{ selectedResult.task_id }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="selectedResult.status === 'success' ? 'success' : 'danger'" size="small">
              {{ selectedResult.status }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(selectedResult.created_at) }}</el-descriptions-item>
        </el-descriptions>
        <div class="json-section">
          <div class="json-section__title">结果数据</div>
          <pre class="json-block">{{ formatJson(selectedResult.data || selectedResult.result) }}</pre>
        </div>
        <div v-if="selectedResult.error" class="json-section">
          <div class="json-section__title">错误信息</div>
          <pre class="json-block json-block--error">{{ selectedResult.error }}</pre>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getResults, getResult, deleteResult } from '@/api/template'
import PageToolbar from '@/components/PageToolbar.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'

const loading = ref(false)
const results = ref([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const filterValues = ref({ task_id: '', search: '' })
const FILTERS = [
  { key: 'task_id', type: 'input', label: '任务 ID', placeholder: '输入任务 ID' },
  { key: 'search', type: 'input', label: '搜索', placeholder: '关键词搜索' },
]

// Viewer
const viewerVisible = ref(false)
const selectedResult = ref(null)

function formatTime(str) {
  if (!str) return '-'
  return new Date(str).toLocaleString('zh-CN')
}

function formatJson(data) {
  if (!data) return '-'
  try {
    return typeof data === 'string' ? JSON.stringify(JSON.parse(data), null, 2) : JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

function clearFilters() {
  filterValues.value = { task_id: '', search: '' }
  page.value = 1
  loadResults()
}

async function loadResults() {
  loading.value = true
  try {
    const params = {
      page: page.value,
      per_page: pageSize.value,
      ...filterValues.value,
    }
    Object.keys(params).forEach(k => { if (!params[k]) delete params[k] })
    const res = await getResults(params)
    const data = res?.data || res || {}
    results.value = data.results || data.items || data || []
    total.value = data.total || results.value.length
  } catch {
    results.value = []
  } finally {
    loading.value = false
  }
}

async function viewResult(row) {
  try {
    const res = await getResult(row.id)
    selectedResult.value = res?.data || res || row
  } catch {
    selectedResult.value = row
  }
  viewerVisible.value = true
}

async function handleDelete(row) {
  try {
    await deleteResult(row.id)
    ElMessage.success('已删除')
    loadResults()
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(loadResults)
</script>

<style lang="scss" scoped>
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.mb-3 { margin-bottom: 12px; }
.mb-4 { margin-bottom: 16px; }

.result-detail {
  max-height: 70vh;
  overflow-y: auto;
}

.json-section {
  margin-top: 16px;

  &__title {
    font-weight: 600;
    margin-bottom: 8px;
    color: var(--app-text);
  }
}

.json-block {
  background: #0b1220;
  color: #93c5fd;
  padding: 16px;
  border-radius: var(--el-border-radius-base);
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.6;
  max-height: 400px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;

  &--error {
    color: #f87171;
  }
}

.cell-time {
  font-size: var(--app-font-sm);
  color: var(--app-text-muted);
  white-space: nowrap;
}
</style>
