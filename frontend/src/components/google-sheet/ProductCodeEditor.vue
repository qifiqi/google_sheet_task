<script setup lang="ts">
import { computed, shallowRef } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const model = defineModel<string>({ required: true })
const input = shallowRef('')
type ProductCode = string | number

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

function addCodes() {
  const codes = input.value.split(/[，,\s]+/).map((item) => item.trim()).filter(Boolean)
  if (!codes.length) return
  if (parsedCodes.value.error) {
    ElMessage.error(parsedCodes.value.error)
    return
  }
  const existing = new Set(parsedCodes.value.codes.map(String))
  const next = [...parsedCodes.value.codes]
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
      <el-tag v-for="(code, index) in parsedCodes.codes" :key="`${String(code)}-${index}`" closable effect="plain" @close="removeCode(code)">{{ code }}</el-tag>
    </div>
    <el-alert v-if="parsedCodes.error" :title="parsedCodes.error" type="warning" :closable="false" show-icon />
    <el-form-item label="产品代码 JSON（高级）">
      <el-input v-model="model" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder='例如：["000001", "600519"]' />
    </el-form-item>
  </section>
</template>

<style scoped>
.product-code-editor { display: grid; gap: 10px; }
.product-code-editor :deep(.el-form-item) { margin-bottom: 0; }
.product-code-editor__input-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
.product-code-editor__tags { display: flex; flex-wrap: wrap; gap: 6px; min-height: 28px; padding: 8px 10px; border: 1px solid var(--admin-border-light); border-radius: 6px; background: var(--admin-bg); }
@media (max-width: 560px) { .product-code-editor__input-row { grid-template-columns: 1fr; } }
</style>
