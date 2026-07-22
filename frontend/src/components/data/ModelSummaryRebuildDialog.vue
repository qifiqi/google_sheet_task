<script setup lang="ts">
import { reactive, watch } from 'vue'

const open = defineModel<boolean>({ default: false })
const props = defineProps<{ loading: boolean; defaultTaskType: string }>()
const emit = defineEmits<{ start: [options: { taskType: string; taskId: string; batchSize: number; reset: boolean }] }>()
const form = reactive({ taskType: '', taskId: '', batchSize: 20, reset: false })

watch(open, (visible) => {
  if (!visible) return
  form.taskType = props.defaultTaskType
  form.taskId = ''
  form.batchSize = 20
  form.reset = false
})
</script>

<template>
  <el-dialog v-model="open" title="重建汇总索引" width="min(520px, calc(100vw - 32px))" :close-on-click-modal="false">
    <el-alert title="索引重建在后台执行，不会中断已有任务。" type="info" :closable="false" show-icon />
    <el-form class="model-summary-rebuild" label-position="top">
      <el-form-item label="任务类型"><el-select v-model="form.taskType" clearable placeholder="全部支持类型"><el-option label="C3" value="google_sheet" /><el-option label="C4" value="google_sheet_C4" /><el-option label="C5" value="google_sheet_C5" /><el-option label="C7" value="google_sheet_C7" /><el-option label="回测" value="backtest_training" /></el-select></el-form-item>
      <el-form-item label="任务 ID"><el-input v-model="form.taskId" clearable placeholder="留空则按任务类型重建" /></el-form-item>
      <el-form-item label="批处理大小"><el-input-number v-model="form.batchSize" :min="1" :max="200" controls-position="right" /></el-form-item>
      <el-form-item><el-checkbox v-model="form.reset">先清空已存在的索引记录</el-checkbox></el-form-item>
    </el-form>
    <template #footer><el-button @click="open = false">取消</el-button><el-button type="primary" :loading="loading" @click="emit('start', { ...form })">开始重建</el-button></template>
  </el-dialog>
</template>

<style scoped>
.model-summary-rebuild { margin-top: 18px; }.model-summary-rebuild :deep(.el-select),.model-summary-rebuild :deep(.el-input),.model-summary-rebuild :deep(.el-input-number) { width: 100%; }
</style>
