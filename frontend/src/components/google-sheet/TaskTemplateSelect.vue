<script setup lang="ts">
interface TaskTemplateOption {
  label: string
  value: number
}

const props = withDefaults(defineProps<{
  options: TaskTemplateOption[]
  loading?: boolean
}>(), { loading: false })

const model = defineModel<number>()
const emit = defineEmits<{ change: [templateId: number | undefined] }>()

function normalizeTemplateId(value: unknown) {
  const templateId = Number(value)
  return Number.isInteger(templateId) && templateId > 0 ? templateId : undefined
}

function updateTemplateId(value: unknown) {
  model.value = normalizeTemplateId(value)
}

function selectTemplate(value: unknown) {
  emit('change', normalizeTemplateId(value))
}
</script>

<template>
  <el-select
    class="task-template-select"
    :model-value="model"
    clearable
    :loading="props.loading"
    persistent
    popper-class="c-series-fast-select"
    placeholder="不使用模板"
    @update:model-value="updateTemplateId"
    @change="selectTemplate"
  >
    <el-option
      v-if="model && !props.options.some((option) => option.value === model)"
      :label="`当前模板 #${model}`"
      :value="model"
    />
    <el-option v-for="option in props.options" :key="option.value" :label="option.label" :value="option.value" />
  </el-select>
</template>

<style scoped>
.task-template-select { width: 100%; }
</style>
