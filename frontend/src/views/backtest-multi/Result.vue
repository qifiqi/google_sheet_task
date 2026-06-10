<template>
  <div class="backtest-multi-result-page" v-loading="loading">
    <PageToolbar eyebrow="多产品回测结果" :title="resultTitle">
      <template #actions>
        <el-button type="primary" plain @click="handleExport" :loading="exporting">
          <el-icon style="margin-right: 4px"><Download /></el-icon>导出
        </el-button>
        <el-button plain @click="router.push(`/backtest-multi/${taskId}`)">返回详情</el-button>
      </template>
    </PageToolbar>

    <StatCardGrid
      v-if="summaryCards.length"
      :cards="summaryCards"
      :data="summaryData"
      :columns="{ xs: 12, sm: 8, md: 6 }"
      class="mb-4"
    />

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>结果数据</span>
          <el-button size="small" @click="loadResult">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>

      <el-table :data="resultRows" stripe border style="width: 100%" max-height="600">
        <el-table-column
          v-for="col in tableColumns"
          :key="col.prop"
          :prop="col.prop"
          :label="col.label"
          :width="col.width"
          :min-width="col.minWidth"
          show-overflow-tooltip
        />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Download, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getTaskResult, exportGlobalPreview } from '@/api/backtestMulti'
import PageToolbar from '@/components/PageToolbar.vue'
import StatCardGrid from '@/components/StatCardGrid.vue'

const route = useRoute()
const router = useRouter()
const taskId = computed(() => route.params.id)

const loading = ref(false)
const exporting = ref(false)
const result = ref(null)

const resultTitle = computed(() => result.value?.task_name || `多产品回测结果 #${taskId.value}`)

const summaryCards = computed(() => {
  if (!result.value?.summary) return []
  return Object.keys(result.value.summary).map(key => ({
    key,
    label: key,
  }))
})

const summaryData = computed(() => result.value?.summary || {})

const resultRows = computed(() => {
  if (!result.value) return []
  return result.value.rows || result.value.data || result.value.results || []
})

const tableColumns = computed(() => {
  const rows = resultRows.value
  if (!rows.length) return []
  const first = rows[0]
  return Object.keys(first).map(key => ({
    prop: key,
    label: key,
    minWidth: 120,
  }))
})

async function loadResult() {
  loading.value = true
  try {
    const res = await getTaskResult(taskId.value)
    result.value = res.data || res
  } catch {
    result.value = null
    ElMessage.error('加载结果失败')
  } finally {
    loading.value = false
  }
}

async function handleExport() {
  exporting.value = true
  try {
    const res = await exportGlobalPreview(taskId.value)
    const blob = new Blob([res], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `backtest_multi_result_${taskId.value}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

onMounted(loadResult)
</script>

<style lang="scss" scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
