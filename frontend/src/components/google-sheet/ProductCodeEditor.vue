<script setup lang="ts">
import { computed, shallowRef } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const model = defineModel<string>({ required: true })
const input = shallowRef('')
const showAllCodes = shallowRef(false)
type ProductCode = string | number
const defaultVisibleCodeCount = 24

const parsedCodes = computed(() => {
  const value = model.value.trim()
  if (!value) return { codes: [] as ProductCode[], error: '' }
  try {
    const parsed = JSON.parse(value)
    if (!Array.isArray(parsed) || parsed.some((item) => typeof item !== 'string' && typeof item !== 'number')) {
      return { codes: [] as ProductCode[], error: '参数一必须是产品代码数组' }
    }
    return { codes: parsed as ProductCode[], error: '' }
  } catch {
    return { codes: [] as ProductCode[], error: '参数一 JSON 格式有误，请修正后再添加代码' }
  }
})

const visibleCodes = computed(() => showAllCodes.value ? parsedCodes.value.codes : parsedCodes.value.codes.slice(0, defaultVisibleCodeCount))
const hiddenCodeCount = computed(() => Math.max(0, parsedCodes.value.codes.length - defaultVisibleCodeCount))

function addCodes() {
  const codes = input.value.split(/[，,\s]+/).map((item) => item.trim()).filter(Boolean)
  if (!codes.length) return
  if (parsedCodes.value.error) ElMessage.warning('已用新输入覆盖原有的无效产品代码')
  const currentCodes = parsedCodes.value.error ? [] : parsedCodes.value.codes
  const existing = new Set(currentCodes.map(String))
  const next = [...currentCodes]
  codes.forEach((code) => {
    if (!existing.has(code)) {
      next.push(code)
      existing.add(code)
    }
  })
  model.value = JSON.stringify(next)
  input.value = ''
}

function removeCode(code: ProductCode) {
  model.value = JSON.stringify(parsedCodes.value.codes.filter((item) => String(item) !== String(code)))
}
</script>

<template>
  <section class="product-code-editor">
    <el-form-item label="股票/产品代码" required>
      <div class="product-code-editor__input-row">
        <el-input v-model="input" placeholder="例如：600000, 600001 或 600000 600001" @keyup.enter.prevent="addCodes" />
        <el-button type="primary" :icon="Plus" @click="addCodes">添加</el-button>
      </div>
    </el-form-item>
    <div v-if="parsedCodes.codes.length" class="product-code-editor__tags" aria-label="已添加的产品代码">
      <el-tag v-for="(code, index) in visibleCodes" :key="`${String(code)}-${index}`" closable effect="plain" @close="removeCode(code)">{{ code }}</el-tag>
      <el-button v-if="hiddenCodeCount && !showAllCodes" link type="primary" @click="showAllCodes = true">其余 {{ hiddenCodeCount }} 个</el-button>
      <el-button v-else-if="hiddenCodeCount" link type="primary" @click="showAllCodes = false">收起</el-button>
    </div>
    <el-alert v-if="parsedCodes.error" :title="parsedCodes.error" type="warning" :closable="false" show-icon />
  </section>
</template>

<style scoped>
.product-code-editor { display: grid; min-width: 0; gap: 10px; }
.product-code-editor :deep(.el-form-item), .product-code-editor :deep(.el-form-item__content) { min-width: 0; margin-bottom: 0; }
.product-code-editor__input-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; width: 100%; }
.product-code-editor__tags { display: flex; flex-wrap: wrap; gap: 6px; min-height: 28px; padding: 8px 10px; border: 1px solid var(--admin-border-light); border-radius: 6px; background: var(--admin-bg); }
@media (max-width: 560px) { .product-code-editor__input-row { grid-template-columns: 1fr; } }
</style>
