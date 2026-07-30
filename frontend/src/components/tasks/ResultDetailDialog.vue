<script setup lang="ts">
import { computed, shallowRef, watch } from 'vue'
import { CopyDocument } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import VueJsonPretty from 'vue-json-pretty'
import 'vue-json-pretty/lib/styles.css'
import type { TaskResultDetail, TaskResultPresentationModel, TaskResultPresentationSection } from '../../types/api'
import { formatDateTime } from '../../utils/format'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ result: TaskResultDetail | null; modelKey?: string | null }>()
const activeNames = shallowRef<string[]>([])

const presentationModel = computed<TaskResultPresentationModel | null>(() => {
  const models = props.result?.presentation?.models || []
  return models.find((model) => model.key === props.modelKey) || models[0] || null
})
const coreSection = computed<TaskResultPresentationSection | null>(() => presentationModel.value?.sections.find((section) => section.key === 'core') || null)
const secondarySections = computed(() => presentationModel.value?.sections.filter((section) => section.key !== 'core') || [])
const drawerTitle = computed(() => presentationModel.value ? `结果详情 - ${presentationModel.value.name}` : '结果详情')
const rawModel = computed<any>(() => {
  if (!props.result?.result || typeof props.result.result !== 'object') return props.result?.result || {}
  if (props.modelKey && props.modelKey in (props.result.result as Record<string, unknown>)) return (props.result.result as Record<string, unknown>)[props.modelKey]
  return props.result.result
})
const parameterData = computed<any>(() => props.result?.parameters || {})
const stockCode = computed(() => props.result?.summary?.stock_code || '-')

watch(() => [open.value, props.result?.id, props.modelKey], () => { activeNames.value = [] }, { immediate: true })

async function copyResult() {
  if (!props.result) return
  try {
    await navigator.clipboard.writeText(JSON.stringify(rawModel.value, null, 2))
    ElMessage.success('完整结果已复制')
  } catch {
    ElMessage.error('复制失败，请手动选择数据')
  }
}
</script>

<template>
  <el-drawer
    v-model="open"
    :title="drawerTitle"
    direction="rtl"
    size="min(820px, 96vw)"
    append-to-body
    destroy-on-close
    class="result-detail-drawer"
  >
    <template v-if="result">
      <el-descriptions :column="2" border class="result-detail-drawer__context">
        <el-descriptions-item label="结果 ID">{{ result.id }}</el-descriptions-item>
        <el-descriptions-item label="执行状态"><el-tag :type="result.success ? 'success' : 'danger'" effect="light">{{ result.success ? '成功' : '失败' }}</el-tag></el-descriptions-item>
        <el-descriptions-item label="股票代码">{{ stockCode }}</el-descriptions-item>
        <el-descriptions-item label="K 线区间">{{ result.summary?.kline_date_range || result.summary?.period || '-' }}</el-descriptions-item>
        <el-descriptions-item label="执行步骤">{{ result.step_index ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="记录时间">{{ formatDateTime(result.timestamp) }}</el-descriptions-item>
        <el-descriptions-item v-if="result.summary?.parameter_items?.length" label="参数组合" :span="2">
          <span class="result-detail-drawer__parameters"><el-tag v-for="item in result.summary.parameter_items" :key="item.label" effect="plain">{{ item.label }}：{{ item.value }}</el-tag></span>
        </el-descriptions-item>
      </el-descriptions>

      <section v-if="coreSection" class="result-detail-drawer__main-section">
        <header><h3>{{ coreSection.title }}</h3><span>{{ coreSection.items.length }} 项</span></header>
        <el-descriptions :column="2" border class="result-detail-drawer__metrics">
          <el-descriptions-item v-for="item in coreSection.items" :key="item.label" :label="item.label">{{ item.value }}</el-descriptions-item>
        </el-descriptions>
      </section>
      <el-empty v-else description="暂无可展示的回测指标" :image-size="56" />

      <el-collapse v-model="activeNames" class="result-detail-drawer__secondary">
        <el-collapse-item v-for="section in secondarySections" :key="section.key" :name="section.key">
          <template #title><span>{{ section.title }}</span><small>{{ section.items.length }} 项</small></template>
          <el-descriptions :column="2" border><el-descriptions-item v-for="item in section.items" :key="item.label" :label="item.label">{{ item.value }}</el-descriptions-item></el-descriptions>
        </el-collapse-item>
        <el-collapse-item name="parameters">
          <template #title><span>输入参数</span><small>原始结构化数据</small></template>
          <div class="result-detail-drawer__json"><VueJsonPretty :data="parameterData" :deep="2" show-line-number show-length /></div>
        </el-collapse-item>
        <el-collapse-item name="raw-result">
          <template #title><span>完整结果数据</span><small>仅用于核对与排查</small></template>
          <div class="result-detail-drawer__json"><VueJsonPretty :data="rawModel" :deep="2" show-line-number show-length /></div>
        </el-collapse-item>
        <el-collapse-item v-if="result.error_message" name="error">
          <template #title><span>错误信息</span></template>
          <pre class="result-detail-drawer__error">{{ result.error_message }}</pre>
        </el-collapse-item>
      </el-collapse>
    </template>
    <el-skeleton v-else :rows="8" animated />
    <template #footer><el-button :icon="CopyDocument" @click="copyResult">复制完整数据</el-button><el-button type="primary" @click="open = false">关闭</el-button></template>
  </el-drawer>
</template>

<style scoped>
.result-detail-drawer__context,
.result-detail-drawer__metrics {
  width: 100%;
}

.result-detail-drawer__parameters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.result-detail-drawer__main-section {
  display: grid;
  gap: 10px;
  margin-top: 18px;
}

.result-detail-drawer__main-section header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.result-detail-drawer__main-section h3 {
  margin: 0;
  color: var(--admin-text);
  font-size: 16px;
  font-weight: 600;
}

.result-detail-drawer__main-section header span,
.result-detail-drawer__secondary small {
  color: var(--admin-text-muted);
  font-size: 12px;
}

.result-detail-drawer__secondary {
  margin-top: 18px;
  border-top: 1px solid var(--admin-border-light);
  border-bottom: 1px solid var(--admin-border-light);
}

.result-detail-drawer__secondary :deep(.el-collapse-item__header),
.result-detail-drawer__secondary :deep(.el-collapse-item__wrap) {
  border-bottom: 0;
  background: transparent;
}

.result-detail-drawer__secondary :deep(.el-collapse-item__content) {
  padding-bottom: 12px;
}

.result-detail-drawer__secondary small {
  margin-left: 8px;
}

.result-detail-drawer__json {
  max-height: 360px;
  overflow: auto;
  padding: 12px;
  border: 1px solid var(--admin-border-light);
  border-radius: 6px;
  background: var(--admin-bg);
}

.result-detail-drawer__error {
  max-height: 240px;
  margin: 0;
  padding: 12px;
  overflow: auto;
  border: 1px solid var(--admin-border-light);
  border-radius: 6px;
  background: var(--admin-bg);
  color: var(--admin-text-regular);
  font: 12px/20px Consolas, "Courier New", monospace;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 640px) {
  .result-detail-drawer__context,
  .result-detail-drawer__metrics,
  .result-detail-drawer__secondary :deep(.el-descriptions) {
    overflow: auto;
  }

  .result-detail-drawer__context :deep(.el-descriptions__table),
  .result-detail-drawer__metrics :deep(.el-descriptions__table),
  .result-detail-drawer__secondary :deep(.el-descriptions__table) {
    min-width: 560px;
  }
}
</style>
