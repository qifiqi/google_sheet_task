<template>
  <div class="app-page global-preview-page">
    <PageToolbar
      eyebrow="GLOBAL PREVIEW"
      title="单品全局预览"
      description="输入回测任务 ID，按年份或股票分组查看全部参数方案的指标对比。"
    >
      <template #actions>
        <el-input
          v-model="taskIdInput"
          placeholder="任务 ID"
          class="preview-task-input"
          @keyup.enter="queryTask"
        />
        <el-button type="primary" :loading="loadingTask" @click="queryTask">查询</el-button>
      </template>
    </PageToolbar>

    <el-card v-if="supported === false" shadow="never" class="page-section">
      <el-empty :description="unsupportedMessage || '该任务不支持全局预览'" />
    </el-card>

    <template v-if="previewPayload">
      <el-card shadow="never" class="page-section">
        <div class="control-row">
          <el-select
            v-if="groupMode === 'stock'"
            v-model="activeStockCode"
            class="preview-select"
            @change="onStockChange"
          >
            <el-option v-for="stock in stockOptions" :key="stock" :label="stock" :value="stock" />
          </el-select>
          <el-select v-model="activeGroupKey" class="preview-select" @change="onGroupChange">
            <el-option v-for="group in groupOptions" :key="group.value" :label="group.label" :value="group.value" />
          </el-select>
          <div class="control-row--stretch">
            <el-input v-model="exportName" placeholder="导出文件名" />
            <el-button :loading="exporting" @click="exportPreview">导出</el-button>
          </div>
        </div>
        <div v-if="groupMeta" class="helper-text">{{ groupMeta }}</div>
      </el-card>

      <el-card v-loading="loadingGroup" shadow="never" class="page-section">
        <el-table v-if="activeGroup" :data="tableRows" border stripe size="small">
          <el-table-column prop="category" label="指标类型" width="110" fixed="left" />
          <el-table-column prop="metric" label="指标" width="150" fixed="left" />
          <el-table-column prop="index_value" label="指数" width="110" />
          <el-table-column
            v-for="column in activeGroup.columns"
            :key="column.column_key"
            :label="column.header || `结果 ${column.result_id}`"
            min-width="120"
            align="right"
          >
            <template #header>
              <div class="preview-column-head">
                <div>{{ column.header || `结果 ${column.result_id}` }}</div>
                <small>结果 ID: {{ column.result_id }}</small>
              </div>
            </template>
            <template #default="{ row }">
              {{ row.values?.[column.column_key] || '-' }}
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="该分组下没有成功结果" />
      </el-card>
    </template>

    <el-card v-else shadow="never" class="page-section">
      <el-empty description="输入任务 ID 查询全局预览" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { getPreviewTask, previewGroup } from '@/api/globalPreview'
import { rawApi } from '@/api'

const taskIdInput = ref('')
const currentTaskId = ref('')
const supported = ref(null)
const unsupportedMessage = ref('')
const groupMode = ref('year')
const previewGroups = ref([])
const previewCache = new Map()
const previewPayload = ref(null)
const activeStockCode = ref('')
const activeGroupKey = ref('')
const exportName = ref('')
const loadingTask = ref(false)
const loadingGroup = ref(false)
const exporting = ref(false)

const previewGroupList = computed(() => previewPayload.value?.groups || [])

const stockOptions = computed(() =>
  previewGroupList.value.map((group) => group.stock_code).filter((code, index, list) => list.indexOf(code) === index)
)

const groupsForActiveStock = computed(() =>
  previewGroupList.value.filter((group) => group.stock_code === activeStockCode.value)
)

const groupOptions = computed(() => {
  if (groupMode.value === 'year') {
    return previewGroups.value.map((group) => ({
      value: group.key,
      label: `${group.label} (${group.result_ids.length} 组参数)`,
    }))
  }
  return groupsForActiveStock.value.map((group) => ({
    value: group.group_key,
    label: `${group.group_label} (${group.column_count || 0} 组参数)`,
  }))
})

const activeGroup = computed(() => {
  if (groupMode.value === 'year') {
    return previewGroupList.value.find((item) => item.year === activeGroupKey.value)
  }
  return groupsForActiveStock.value.find((item) => item.group_key === activeGroupKey.value)
})

const groupMeta = computed(() => activeGroup.value?.period || '')

const tableRows = computed(() => (activeGroup.value?.rows || []).length ? activeGroup.value.rows : [])

function activeMetadataGroup() {
  if (groupMode.value === 'stock') {
    return previewGroups.value.find((group) => group.key === activeStockCode.value)
  }
  return previewGroups.value.find((group) => group.key === activeGroupKey.value)
}

async function loadMetadataGroup(group, loadingText) {
  if (!group) return
  if (previewCache.has(group.key)) {
    previewPayload.value = previewCache.get(group.key)
    return
  }
  loadingGroup.value = true
  try {
    const data = await previewGroup(encodeURIComponent(currentTaskId.value), { result_ids: group.result_ids })
    previewPayload.value = data?.preview
    previewCache.set(group.key, previewPayload.value)
  } catch (error) {
    ElMessage.error(error.message || `${loadingText || '分组'}加载失败`)
  } finally {
    loadingGroup.value = false
  }
}

function onStockChange() {
  activeGroupKey.value = ''
  if (groupMode.value === 'stock') {
    loadMetadataGroup(activeMetadataGroup(), activeStockCode.value)
  }
}

function onGroupChange() {
  if (groupMode.value === 'year') {
    loadMetadataGroup(activeMetadataGroup(), activeGroupKey.value)
  }
}

async function queryTask() {
  const taskId = taskIdInput.value.trim()
  if (!taskId) {
    ElMessage.warning('请输入任务 ID')
    return
  }
  currentTaskId.value = taskId
  loadingTask.value = true
  try {
    const data = await getPreviewTask(encodeURIComponent(taskId))
    if (!data.supported) {
      supported.value = false
      unsupportedMessage.value = data.message || ''
      previewPayload.value = null
      return
    }
    supported.value = true
    groupMode.value = data.initial?.group_mode || 'year'
    previewGroups.value = data.initial?.groups || []
    previewCache.clear()
    const initialPreview = data.initial?.preview || data.preview
    previewPayload.value = initialPreview
    const defaultKey = data.initial?.default_group_key || previewGroups.value[0]?.key || ''
    if (initialPreview) previewCache.set(defaultKey, initialPreview)
    activeStockCode.value = groupMode.value === 'stock'
      ? defaultKey
      : (initialPreview?.groups?.[0]?.stock_code || '')
    activeGroupKey.value = groupMode.value === 'year' ? defaultKey : ''
    exportName.value = initialPreview?.task?.name || taskId
  } catch (error) {
    ElMessage.error(error.message || '查询失败')
  } finally {
    loadingTask.value = false
  }
}

async function exportPreview() {
  if (!currentTaskId.value) return
  exporting.value = true
  try {
    const blob = await rawApi.get(`/api/exports/global-previews/${encodeURIComponent(currentTaskId.value)}`, {
      params: exportName.value.trim() ? { export_name: exportName.value.trim() } : undefined,
      responseType: 'blob',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${exportName.value.trim() || 'global_preview'}.xlsx`
    link.click()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.preview-task-input {
  width: 260px;
}

.preview-select {
  width: 260px;
}

.preview-column-head small {
  font-weight: 400;
  color: var(--app-text-muted);
}
</style>
