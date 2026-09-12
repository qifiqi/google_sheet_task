<template>
  <div class="app-page admin-results-page">
    <PageToolbar eyebrow="管理后台" title="结果查询">
      <template #actions>
        <el-input
          v-model="taskIdFilter"
          placeholder="输入任务 ID 筛选"
          clearable
          class="results-filter-input"
          @keyup.enter="doFilter"
          @clear="doFilter"
        >
          <template #append>
            <el-button @click="doFilter">搜索</el-button>
          </template>
        </el-input>
      </template>
    </PageToolbar>

    <DataTableCard
      :data="results"
      :loading="loading"
      :total="total"
      :page="page"
      :page-size="pageSize"
      :page-sizes="[10, 20, 50, 100]"
      @update:page="page = $event"
      @update:page-size="pageSize = $event"
      @page-change="loadResults"
    >
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="task_id" label="任务 ID" min-width="200" show-overflow-tooltip />
      <el-table-column prop="step_index" label="步骤索引" width="90" />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.success ? 'success' : 'danger'" size="small">{{ row.success ? '成功' : '失败' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="timestamp" label="时间" width="180" />
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button link type="primary" @click="viewResult(row.id)">查看</el-button>
          <el-button link type="danger" @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </DataTableCard>

    <el-drawer v-model="drawerVisible" title="结果详情" :size="isMobile ? '100%' : '600px'">
      <div v-if="currentResult" class="result-drawer">
        <section class="result-section">
          <h4 class="section-label">参数信息</h4>
          <pre class="mono-pre result-block result-block--limited">{{ JSON.stringify(currentResult.parameters, null, 2) }}</pre>
        </section>
        <section class="result-section">
          <h4 class="section-label">执行结果</h4>
          <pre class="mono-pre result-block result-block--limited">{{ JSON.stringify(currentResult.result, null, 2) }}</pre>
        </section>
        <section v-if="currentResult.error_message" class="result-section">
          <h4 class="section-label">错误信息</h4>
          <pre class="mono-pre mono-pre--danger result-block">{{ currentResult.error_message }}</pre>
        </section>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getResults, getResult, deleteResult } from '@/api/template'
import { useResponsive } from '@/composables/useResponsive'
import PageToolbar from '@/components/PageToolbar.vue'
import DataTableCard from '@/components/DataTableCard.vue'

const route = useRoute()
const { isMobile } = useResponsive()
const results = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const taskIdFilter = ref('')
const drawerVisible = ref(false)
const currentResult = ref(null)

async function loadResults() {
  loading.value = true
  try {
    const params = { page: page.value, per_page: pageSize.value }
    if (taskIdFilter.value) params.task_id = taskIdFilter.value
    const res = await getResults(params)
    results.value = res.results || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

function doFilter() {
  page.value = 1
  loadResults()
}

async function viewResult(id) {
  try {
    const res = await getResult(id)
    currentResult.value = res
    drawerVisible.value = true
  } catch {
    ElMessage.error('加载结果详情失败')
  }
}

async function handleDelete(id) {
  await ElMessageBox.confirm('确定要删除这条结果记录吗？', '确认删除', { type: 'warning' })
  await deleteResult(id)
  ElMessage.success('删除成功')
  loadResults()
}

onMounted(() => {
  if (route.query.task_id) taskIdFilter.value = route.query.task_id
  loadResults()
})
</script>

<style scoped>
.results-filter-input {
  width: 280px;
}

.result-drawer {
  display: grid;
  gap: 18px;
}

.result-section {
  display: grid;
  gap: 10px;
}

.result-block {
  max-height: 300px;
}

.result-block--limited {
  max-height: 300px;
}

@media (max-width: 767px) {
  .results-filter-input {
    width: 100%;
  }
}
</style>
