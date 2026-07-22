<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { TaskItem } from '../../types/api'

const props = defineProps<{
  modelValue: boolean
  tasks: TaskItem[]
  submitting: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [visible: boolean]
  submit: [options: { resumeFromCheckpoint: boolean; delaySeconds: number }]
}>()

const restartMode = ref<'checkpoint' | 'fresh'>('checkpoint')
const delaySeconds = ref(2)
const visible = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})

watch(visible, value => {
  if (value) {
    restartMode.value = 'checkpoint'
    delaySeconds.value = 2
  }
})

function submit() {
  emit('submit', {
    resumeFromCheckpoint: restartMode.value === 'checkpoint',
    delaySeconds: delaySeconds.value,
  })
}
</script>

<template>
  <el-dialog v-model="visible" title="批量重启任务" width="520px" :close-on-click-modal="!submitting" :close-on-press-escape="!submitting" :show-close="!submitting">
    <div class="batch-restart-dialog">
      <p>将按当前顺序逐个提交 {{ tasks.length }} 个任务，前一个请求完成后再等待指定时间。</p>
      <el-form label-position="top">
        <el-form-item label="重启方式">
          <el-radio-group v-model="restartMode" :disabled="submitting">
            <el-radio-button value="checkpoint">断点重启</el-radio-button>
            <el-radio-button value="fresh">从头重启</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="任务间等待时间">
          <el-input-number v-model="delaySeconds" :min="1" :max="60" :step="1" :disabled="submitting" />
          <span class="batch-restart-dialog__unit">秒</span>
        </el-form-item>
      </el-form>
      <div class="batch-restart-dialog__tasks" aria-label="待重启任务">
        <strong>已选任务</strong>
        <ul>
          <li v-for="task in tasks" :key="task.id">{{ task.name }}</li>
        </ul>
      </div>
    </div>
    <template #footer>
      <el-button :disabled="submitting" @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">开始重启</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.batch-restart-dialog { display: grid; gap: 16px; }
.batch-restart-dialog > p { margin: 0; color: var(--admin-text-regular); line-height: 1.6; }
.batch-restart-dialog :deep(.el-form-item) { margin-bottom: 14px; }
.batch-restart-dialog :deep(.el-form-item:last-child) { margin-bottom: 0; }
.batch-restart-dialog__unit { margin-left: 8px; color: var(--admin-text-muted); font-size: 13px; }
.batch-restart-dialog__tasks { display: grid; gap: 8px; padding: 12px; border: 1px solid var(--admin-border-light); background: var(--admin-fill-light); }
.batch-restart-dialog__tasks strong { color: var(--admin-text); font-size: 13px; }
.batch-restart-dialog__tasks ul { display: grid; gap: 4px; max-height: 160px; margin: 0; padding-left: 20px; overflow-y: auto; color: var(--admin-text-regular); font-size: 13px; }
.batch-restart-dialog__tasks li { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
