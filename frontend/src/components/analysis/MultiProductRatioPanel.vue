<script setup lang="ts">
import { DocumentChecked, Operation } from '@element-plus/icons-vue'
import type { GlobalPreviewPayload } from '../../types/analysis'
import '../../styles/analysis/multi-product-ratio-panel.css'

defineProps<{
  products: GlobalPreviewPayload['products']
  loading: boolean
}>()

const ratios = defineModel<number[]>('ratios', { required: true })
const emit = defineEmits<{
  preview: []
  save: []
}>()
</script>

<template>
  <section class="multi-product-ratio-panel">
    <div class="multi-product-ratio-panel__header">
      <div><h2>产品比例</h2><span>调整后先计算预览，再保存到任务配置</span></div>
      <div class="multi-product-ratio-panel__actions">
        <el-button :icon="Operation" :loading="loading" @click="emit('preview')">计算预览</el-button>
        <el-button type="primary" :icon="DocumentChecked" :loading="loading" @click="emit('save')">保存比例</el-button>
      </div>
    </div>
    <div class="multi-product-ratio-panel__inputs">
      <label v-for="(product, index) in products || []" :key="`${product.code || product.name || 'product'}-${index}`">
        <span>{{ product.name || product.code || `产品 ${index + 1}` }}</span>
        <el-input-number v-model="ratios[index]" :min="0" :precision="4" :step="0.1" controls-position="right" />
      </label>
    </div>
  </section>
</template>
