<script setup lang="ts">
import { computed } from 'vue'
import { CircleClose, DocumentChecked } from '@element-plus/icons-vue'
import { c31CombinationCount, parseParameterInputs } from '../../utils/google-sheet-form'

const props = withDefaults(defineProps<{ matrix?: boolean }>(), { matrix: false })
const model = defineModel<string[]>({ required: true })

const summary = computed(() => {
  try {
    const groups = parseParameterInputs(model.value, props.matrix)
    return { valid: true, dimensions: groups.length, combinations: groups.length ? (props.matrix ? c31CombinationCount(groups) : groups.reduce((total, item) => total * item.length, 1)) : 0 }
  } catch (error) { return { valid: false, message: error instanceof Error ? error.message : '参数格式错误' } }
})
const inputPlaceholder = computed(() => props.matrix ? '[[1, "A"], [2, "B"]]' : '["value1", "value2"]')

function update(index: number, value: string) { model.value = model.value.map((item, itemIndex) => itemIndex === index ? value : item) }
function clear(index: number) { update(index, '') }
</script>

<template>
  <section class="parameter-editor">
    <header class="parameter-editor__header">
      <div><h2>参数配置</h2><p>{{ matrix ? '每一维可填写一维数组或二维数组；二维数组的每一行作为一个批量组合单元。' : '每一维填写 JSON 一维数组，例如 [1, 2, 3]。' }}</p></div>
      <el-tag :type="summary.valid ? 'success' : 'danger'" effect="light">{{ summary.valid ? `${summary.dimensions || 0} 维 / ${summary.combinations || 0} 个组合` : '格式待修正' }}</el-tag>
    </header>
    <div class="parameter-editor__grid">
      <section v-for="(value, index) in model" :key="index" class="parameter-editor__item">
        <div class="parameter-editor__item-header"><span>参数 {{ index + 1 }}</span><el-button text :icon="CircleClose" aria-label="清空参数" @click="clear(index)" /></div>
        <el-input :model-value="value" type="textarea" :autosize="{ minRows: 4, maxRows: 8 }" :placeholder="inputPlaceholder" @update:model-value="(nextValue) => update(index, nextValue)" />
      </section>
    </div>
    <p v-if="!summary.valid" class="parameter-editor__error"><el-icon><DocumentChecked /></el-icon>{{ summary.message }}</p>
  </section>
</template>

<style scoped>
.parameter-editor { display: grid; gap: 16px; }.parameter-editor__header { display: flex; align-items: start; justify-content: space-between; gap: 16px; }.parameter-editor__header h2 { margin: 0; color: var(--admin-text); font-size: 16px; font-weight: 600; }.parameter-editor__header p { margin: 4px 0 0; color: var(--admin-text-muted); font-size: 13px; line-height: 20px; }.parameter-editor__grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }.parameter-editor__item { overflow: hidden; border: 1px solid var(--admin-border-light); border-radius: 6px; }.parameter-editor__item-header { display: flex; align-items: center; justify-content: space-between; height: 40px; padding: 0 10px 0 12px; border-bottom: 1px solid var(--admin-border-light); color: var(--admin-text-regular); font-size: 13px; font-weight: 600; }.parameter-editor__item :deep(.el-textarea__inner) { border: 0; border-radius: 0; box-shadow: none; font-family: Consolas, "Cascadia Mono", monospace; font-size: 13px; line-height: 20px; }.parameter-editor__error { display: flex; align-items: center; gap: 6px; margin: 0; color: var(--admin-danger); font-size: 13px; }@media (max-width: 1024px) { .parameter-editor__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }@media (max-width: 640px) { .parameter-editor__header { display: grid; }.parameter-editor__grid { grid-template-columns: 1fr; } }
</style>
