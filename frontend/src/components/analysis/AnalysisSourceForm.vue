<script setup lang="ts">
import { reactive } from 'vue'
import { Search } from '@element-plus/icons-vue'
import '../../styles/analysis/analysis-source-form.css'

const props = defineProps<{
  worksheets: readonly string[]
  spreadsheetTitle: string
  loading: boolean
}>()

const emit = defineEmits<{
  fetchWorksheets: [spreadsheetId: string]
  analyze: [payload: { googleSheetUrl: string; spreadsheetId: string; worksheetName: string }]
}>()

const form = reactive({ googleSheetUrl: '', spreadsheetId: '', worksheetName: '' })

function resolveSpreadsheetId() {
  const match = form.googleSheetUrl.match(/\/spreadsheets\/d\/([\w-]+)/)
  form.spreadsheetId = match?.[1] || form.googleSheetUrl.trim()
  if (form.spreadsheetId) emit('fetchWorksheets', form.spreadsheetId)
}

function submit() {
  if (!form.googleSheetUrl || !form.spreadsheetId || !form.worksheetName) return
  emit('analyze', { ...form })
}
</script>

<template>
  <section class="analysis-source-form">
    <el-input v-model="form.googleSheetUrl" clearable placeholder="Google Sheet URL" @change="resolveSpreadsheetId" />
    <el-select v-model="form.worksheetName" :disabled="worksheets.length === 0" placeholder="选择工作表">
      <el-option v-for="worksheet in worksheets" :key="worksheet" :label="worksheet" :value="worksheet" />
    </el-select>
    <el-button :icon="Search" :loading="loading" @click="resolveSpreadsheetId">获取</el-button>
    <el-button type="primary" :disabled="!form.worksheetName" :loading="loading" @click="submit">分析</el-button>
    <span v-if="spreadsheetTitle" class="analysis-source-form__title">{{ spreadsheetTitle }}</span>
  </section>
</template>
