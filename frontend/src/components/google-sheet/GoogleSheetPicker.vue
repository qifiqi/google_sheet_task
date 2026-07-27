<script setup lang="ts">
import { computed, shallowRef, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { requestJson } from '../../api/http'
import type { GoogleSheetItem } from '../../types/system'
import type { GoogleSheetSelection } from '../../types/google-sheet'

const props = withDefaults(defineProps<{
  index?: number
  removable?: boolean
  proxyUrl?: string
  worksheetRequired?: boolean
}>(), { index: 0, removable: false, proxyUrl: '', worksheetRequired: true })

const model = defineModel<GoogleSheetSelection>({ required: true })
const emit = defineEmits<{ remove: [] }>()
const sheets = shallowRef<GoogleSheetItem[]>([])
const worksheets = shallowRef<string[]>([])
const loadingSheets = shallowRef(false)
const loadingWorksheets = shallowRef(false)
const selectedSheet = computed(() => sheets.value.find((item) => item.spreadsheet_id === model.value.spreadsheetId))

function update(patch: Partial<GoogleSheetSelection>) {
  model.value = { ...model.value, ...patch }
}

async function loadSheets() {
  loadingSheets.value = true
  try {
    const payload = await requestJson<{ status: string; items: GoogleSheetItem[] }>('/api/google-sheets?only_available=1')
    sheets.value = payload.items || []
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载 Google Sheet 失败')
  } finally {
    loadingSheets.value = false
  }
}

async function loadWorksheets(spreadsheetId = model.value.spreadsheetId) {
  if (!spreadsheetId) { worksheets.value = []; return }
  loadingWorksheets.value = true
  try {
    const payload = await requestJson<{ status: string; title: string; worksheets: string[] }>('/api/google-sheet/worksheets', {
      method: 'POST', body: JSON.stringify({ spreadsheet_id: spreadsheetId, proxy_url: props.proxyUrl || null }),
    })
    worksheets.value = payload.worksheets || []
    update({ title: model.value.title || payload.title || selectedSheet.value?.name || '', sheetName: model.value.sheetName || payload.worksheets?.[0] || '' })
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载工作表失败')
  } finally {
    loadingWorksheets.value = false
  }
}

function selectSheet(spreadsheetId: string) {
  const selected = sheets.value.find((item) => item.spreadsheet_id === spreadsheetId)
  update({ spreadsheetId, title: selected?.name || '', sheetName: '' })
}

watch(() => model.value.spreadsheetId, (value, previous) => {
  if (value && value !== previous && sheets.value.length) loadWorksheets(value)
})

loadSheets().then(() => { if (model.value.spreadsheetId) loadWorksheets() })
</script>

<template>
  <section class="google-sheet-picker">
    <header v-if="index > 0 || removable" class="google-sheet-picker__header">
      <strong>Sheet {{ index + 1 }}</strong>
      <el-button v-if="removable" link type="danger" @click="emit('remove')">移除</el-button>
    </header>
    <div class="google-sheet-picker__fields">
      <el-form-item label="Google Sheet" required>
        <div class="google-sheet-picker__select-row">
          <el-select :model-value="model.spreadsheetId" filterable :loading="loadingSheets" placeholder="选择可用 Google Sheet" @update:model-value="selectSheet">
            <el-option v-for="item in sheets" :key="item.id" :label="item.name" :value="item.spreadsheet_id" />
          </el-select>
          <el-button :icon="Refresh" aria-label="刷新 Google Sheet" :loading="loadingSheets" @click="loadSheets" />
        </div>
      </el-form-item>
      <el-form-item label="表标题" required>
        <el-input :model-value="model.title" placeholder="选择后自动带出，可调整" @update:model-value="(value) => update({ title: value })" />
      </el-form-item>
      <el-form-item :label="props.worksheetRequired ? '工作表' : '工作表（可选）'" :required="props.worksheetRequired">
        <el-select :model-value="model.sheetName" allow-create filterable :loading="loadingWorksheets" :disabled="!model.spreadsheetId" placeholder="选择或输入工作表" @update:model-value="(value) => update({ sheetName: value })">
          <el-option v-for="worksheet in worksheets" :key="worksheet" :label="worksheet" :value="worksheet" />
        </el-select>
      </el-form-item>
    </div>
  </section>
</template>

<style scoped>
.google-sheet-picker { padding: 16px; border: 1px solid var(--admin-border-light); border-radius: 6px; background: var(--admin-bg); }
.google-sheet-picker__header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; color: var(--admin-text); font-size: 14px; }
.google-sheet-picker__fields { display: grid; grid-template-columns: minmax(220px, 1.5fr) minmax(180px, 1fr) minmax(160px, 0.9fr); gap: 12px; }
.google-sheet-picker__fields :deep(.el-form-item) { margin-bottom: 0; }.google-sheet-picker__fields :deep(.el-select), .google-sheet-picker__fields :deep(.el-input) { width: 100%; }
.google-sheet-picker__select-row { display: grid; grid-template-columns: minmax(0, 1fr) 32px; gap: 8px; width: 100%; }
@media (max-width: 900px) { .google-sheet-picker__fields { grid-template-columns: 1fr; } }
</style>
