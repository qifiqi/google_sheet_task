<script setup lang="ts">
import { computed, shallowRef, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { loadGoogleSheetWorksheets, useAvailableGoogleSheets } from '../../composables/useAvailableGoogleSheets'
import type { GoogleSheetSelectOption } from '../../composables/useAvailableGoogleSheets'
import type { GoogleSheetSelection } from '../../types/google-sheet'

const props = withDefaults(defineProps<{
  index?: number
  removable?: boolean
  proxyUrl?: string
  worksheetRequired?: boolean
  tableType?: string
}>(), { index: 0, removable: false, proxyUrl: '', worksheetRequired: true, tableType: '' })

const model = defineModel<GoogleSheetSelection>({ required: true })
const emit = defineEmits<{ remove: [] }>()
const {
  sheets,
  options: sheetOptions,
  loading: loadingSheets,
  loadSheets: loadAvailableSheets,
} = useAvailableGoogleSheets(props.tableType)
const worksheetOptions = shallowRef<GoogleSheetSelectOption[]>([])
const loadingWorksheets = shallowRef(false)
let worksheetRequestVersion = 0
let loadedWorksheetContext = ''
const selectedSheet = computed(() => sheets.value.find((item) => item.spreadsheet_id === model.value.spreadsheetId))

function update(patch: Partial<GoogleSheetSelection>) {
  model.value = { ...model.value, ...patch }
}

async function loadSheets(force = false) {
  try {
    await loadAvailableSheets(force)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '加载 Google Sheet 失败')
  }
}

async function loadWorksheets(spreadsheetId = model.value.spreadsheetId, force = false) {
  const requestVersion = ++worksheetRequestVersion
  const requestContext = getWorksheetContext(spreadsheetId)
  if (!spreadsheetId) {
    worksheetOptions.value = []
    loadedWorksheetContext = ''
    return
  }
  loadingWorksheets.value = true
  try {
    const payload = await loadGoogleSheetWorksheets({
      spreadsheetId,
      proxyUrl: props.proxyUrl,
      force,
    })
    if (requestVersion !== worksheetRequestVersion || getWorksheetContext() !== requestContext) return
    worksheetOptions.value = payload.options
    loadedWorksheetContext = requestContext
    update({ title: model.value.title || payload.title || selectedSheet.value?.name || '', sheetName: model.value.sheetName || payload.worksheets?.[0] || '' })
  } catch (error) {
    if (requestVersion === worksheetRequestVersion) {
      ElMessage.error(error instanceof Error ? error.message : '加载工作表失败')
    }
  } finally {
    if (requestVersion === worksheetRequestVersion) loadingWorksheets.value = false
  }
}

function getWorksheetContext(spreadsheetId = model.value.spreadsheetId) {
  return JSON.stringify([spreadsheetId, props.proxyUrl.trim()])
}

function selectSheet(spreadsheetId: string) {
  const selected = sheets.value.find((item) => item.spreadsheet_id === spreadsheetId)
  update({ spreadsheetId, title: selected?.name || '', sheetName: '' })
}

function selectWorksheet(sheetName: string) {
  update({ sheetName })
}

function loadWorksheetsWhenOpened(visible: boolean) {
  if (!visible || !model.value.spreadsheetId) return
  if (loadedWorksheetContext === getWorksheetContext()) return
  void loadWorksheets()
}

async function refreshSheets() {
  await loadSheets(true)
  if (model.value.spreadsheetId) await loadWorksheets(model.value.spreadsheetId, true)
}

watch([() => model.value.spreadsheetId, () => props.proxyUrl], ([spreadsheetId, proxyUrl], previous) => {
  if (spreadsheetId === previous?.[0] && proxyUrl === previous?.[1]) return
  worksheetRequestVersion += 1
  worksheetOptions.value = []
  loadedWorksheetContext = ''
  loadingWorksheets.value = false
})

void loadSheets()
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
          <el-select
            :model-value="model.spreadsheetId"
            :loading="loadingSheets"
            persistent
            popper-class="c-series-fast-select"
            placeholder="选择可用 Google Sheet"
            @update:model-value="selectSheet"
          >
            <el-option v-for="option in sheetOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
          <el-button :icon="Refresh" aria-label="刷新 Google Sheet" :loading="loadingSheets || loadingWorksheets" @click="refreshSheets" />
        </div>
      </el-form-item>
      <el-form-item label="表标题" required>
        <el-input :model-value="model.title" placeholder="选择后自动带出，可调整" @update:model-value="(value) => update({ title: value })" />
      </el-form-item>
      <el-form-item :label="props.worksheetRequired ? '工作表' : '工作表（可选）'" :required="props.worksheetRequired">
        <el-select
          :model-value="model.sheetName"
          allow-create
          filterable
          :loading="loadingWorksheets"
          :disabled="!model.spreadsheetId"
          persistent
          popper-class="c-series-fast-select"
          placeholder="选择或输入工作表"
          @visible-change="loadWorksheetsWhenOpened"
          @update:model-value="selectWorksheet"
        >
          <el-option v-for="option in worksheetOptions" :key="option.value" :label="option.label" :value="option.value" />
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
