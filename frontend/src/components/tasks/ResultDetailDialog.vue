<script setup lang="ts">
import { computed } from 'vue'
import { CopyDocument } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { TaskResultDetail } from '../../types/api'
import { formatDateTime } from '../../utils/format'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ result: TaskResultDetail | null; modelKey?: string | null }>()
const parametersText = computed(() => JSON.stringify(props.result?.parameters || {}, null, 2))
const selectedModelResult = computed(() => {
  const payload = props.result?.result
  if (!payload || typeof payload !== 'object' || !props.modelKey) return payload || {}
  const value = (payload as Record<string, unknown>)[props.modelKey]
  return value && typeof value === 'object' ? value : payload
})
const resultText = computed(() => JSON.stringify(selectedModelResult.value, null, 2))
const dialogTitle = computed(() => {
  if (!props.modelKey) return '结果详情'
  const [, ...nameParts] = props.modelKey.split('__')
  return `结果详情 - ${nameParts.join('__') || props.modelKey}`
})

async function copyText() {
  if (!props.result) return
  try { await navigator.clipboard.writeText(JSON.stringify(selectedModelResult.value, null, 2)); ElMessage.success('结果 JSON 已复制') } catch { ElMessage.error('复制失败，请手动选择内容') }
}
</script>

<template>
  <el-dialog v-model="open" :title="dialogTitle" width="min(760px, calc(100vw - 32px))">
    <template v-if="result"><el-descriptions :column="2" border class="result-detail__summary"><el-descriptions-item label="结果 ID">{{ result.id }}</el-descriptions-item><el-descriptions-item label="步骤">{{ result.step_index ?? '-' }}</el-descriptions-item><el-descriptions-item label="任务" :span="2">{{ result.task_name || result.task_id }}</el-descriptions-item><el-descriptions-item label="标的">{{ result.summary?.stock_name ? `${result.summary.stock_code || '-'} / ${result.summary.stock_name}` : result.summary?.stock_code || '-' }}</el-descriptions-item><el-descriptions-item label="执行区间">{{ result.summary?.period || result.summary?.kline_date_range || '-' }}</el-descriptions-item><el-descriptions-item label="参数组合" :span="2"><span v-if="result.summary?.parameter_items?.length" class="result-detail__parameters"><el-tag v-for="item in result.summary.parameter_items" :key="item.label" effect="plain">{{ item.label }}: {{ item.value }}</el-tag></span><span v-else>-</span></el-descriptions-item><el-descriptions-item label="状态"><el-tag :type="result.success ? 'success' : 'danger'">{{ result.success ? '成功' : '失败' }}</el-tag></el-descriptions-item><el-descriptions-item label="记录时间">{{ formatDateTime(result.timestamp) }}</el-descriptions-item></el-descriptions>
      <el-tabs class="result-detail__tabs"><el-tab-pane label="输入参数"><pre>{{ parametersText }}</pre></el-tab-pane><el-tab-pane label="结果数据"><pre>{{ resultText }}</pre></el-tab-pane><el-tab-pane label="错误信息"><pre>{{ result.error_message || '无错误信息' }}</pre></el-tab-pane></el-tabs></template>
    <template #footer><el-button :icon="CopyDocument" @click="copyText">复制 JSON</el-button><el-button type="primary" @click="open = false">关闭</el-button></template>
  </el-dialog>
</template>

<style scoped>
.result-detail__summary { margin-bottom: 16px; }
.result-detail__parameters { display: flex; flex-wrap: wrap; gap: 6px; }
.result-detail__tabs pre { max-height: 360px; margin: 0; padding: 14px; overflow: auto; border: 1px solid var(--admin-border-light); border-radius: 6px; background: var(--admin-bg); color: var(--admin-text-regular); font: 12px/1.6 Consolas, "Courier New", monospace; white-space: pre-wrap; word-break: break-word; }
</style>
