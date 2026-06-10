<template>
  <div class="task-form-core">
    <!-- Basic Info -->
    <el-card shadow="never" class="mb-4">
      <template #header>
        <span class="card-section-title">任务基本信息</span>
      </template>
      <el-form :model="form" label-position="top">
        <el-row :gutter="16">
          <el-col :xs="24" :sm="8">
            <el-form-item label="选择模板">
              <el-select v-model="form.template_id" placeholder="不使用模板" clearable @change="onTemplateChange" style="width: 100%">
                <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
              </el-select>
              <div class="form-hint">选择一个已保存的任务模板来快速填充配置</div>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="任务名称">
              <el-input v-model="form.task_name" placeholder="留空将自动生成任务名称" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="任务描述">
              <el-input v-model="form.task_description" type="textarea" :rows="2" placeholder="描述任务的目的或特殊要求" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- Google Sheet Config -->
    <el-card shadow="never" class="mb-4">
      <template #header>
        <span class="card-section-title">Google Sheet 配置</span>
      </template>
      <el-form :model="form" label-position="top">
        <el-row :gutter="16">
          <el-col :xs="24" :sm="10">
            <el-form-item label="选择 Google Sheet" required>
              <el-select
                v-model="form.spreadsheet_id"
                placeholder="请选择 Google Sheet"
                filterable
                :loading="sheetLoading"
                style="width: 100%"
                @change="onSheetChange"
              >
                <template #prefix>
                  <el-icon @click.stop="refreshSheets"><Refresh /></el-icon>
                </template>
                <el-option v-for="s in sheets" :key="s.spreadsheet_id || s.id" :label="s.name || s.spreadsheet_title" :value="s.spreadsheet_id" />
              </el-select>
              <div class="form-hint">请从列表中选择可用的 Google Sheet</div>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="7">
            <el-form-item label="表标题">
              <el-input v-model="form.spreadsheet_title" placeholder="选择 Google Sheet 后自动带出" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="7">
            <el-form-item label="工作表名称">
              <el-input v-model="form.sheet_name" placeholder="选择 Google Sheet 后自动带出" readonly />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :xs="24" :sm="8">
            <el-form-item label="认证方式">
              <el-select v-model="form.token_type" style="width: 100%">
                <el-option label="Token 文件路径" value="file" />
                <el-option label="Token JSON 字符串" value="json" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item v-if="form.token_type === 'file'" label="Token 文件路径">
              <el-input v-model="form.token_file" placeholder="data/token.json" />
            </el-form-item>
            <el-form-item v-else label="Token JSON 字符串">
              <el-input v-model="form.token_json" type="textarea" :rows="2" placeholder='{"installed": {"client_id": "..."}}' />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="代理 URL (可选)">
              <el-input v-model="form.proxy_url" placeholder="请输入代理 URL" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- Parameters -->
    <el-card shadow="never" class="mb-4">
      <template #header>
        <div class="flex-between">
          <span class="card-section-title">参数配置</span>
          <div class="flex gap-sm">
            <el-button type="primary" plain size="small" @click="addParameter">
              <el-icon><Plus /></el-icon> 添加参数
            </el-button>
            <el-button type="danger" plain size="small" @click="clearParameters">
              <el-icon><Delete /></el-icon> 清空所有
            </el-button>
          </div>
        </div>
      </template>

      <el-row :gutter="12">
        <el-col v-for="(param, idx) in form.parameters" :key="param.id" :xs="24" :sm="12" :md="8" class="mb-3">
          <div class="param-card" :class="`param-card--${PARAM_COLORS[idx % PARAM_COLORS.length]}`">
            <div class="param-card__header">
              <span>参数 {{ idx + 1 }}</span>
              <el-button
                v-if="form.parameters.length > 1"
                text
                size="small"
                type="danger"
                @click="removeParameter(idx)"
              >
                <el-icon><Close /></el-icon>
              </el-button>
            </div>
            <el-input
              v-model="param.values"
              type="textarea"
              :rows="3"
              placeholder='["value1", "value2", "value3"]'
            />
            <div class="form-hint">JSON 数组格式</div>
          </div>
        </el-col>
      </el-row>

      <el-alert v-if="totalCombinations > 0" type="info" :closable="false" show-icon class="mt-3">
        <strong>参数组合：</strong>{{ totalCombinations }} 个参数组合将被执行
      </el-alert>
    </el-card>

    <!-- Actions -->
    <div class="form-actions">
      <el-button @click="$router.back()">返回</el-button>
      <el-button @click="saveAsTemplate">保存为模板</el-button>
      <el-button type="primary" size="large" :loading="submitting" @click="submit">
        创建任务并执行
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Refresh, Plus, Delete, Close } from '@element-plus/icons-vue'
import { getTemplates } from '@/api/template'
import { useTaskForm } from '@/composables/useTaskForm'
import { useGoogleSheetPicker } from '@/composables/useGoogleSheetPicker'

const props = defineProps({
  version: { type: String, default: 'c3' },
})

const {
  form, loading, submitting, parameterCount, totalCombinations,
  addParameter, removeParameter, clearParameters,
  submit, loadTemplate, saveAsTemplate,
} = useTaskForm(props.version)

const { sheets, loading: sheetLoading, loadSheets: refreshSheets, findSheet } = useGoogleSheetPicker()

const templates = ref([])
const PARAM_COLORS = ['primary', 'success', 'info', 'warning', 'danger', '']

async function loadTemplates() {
  try {
    const res = await getTemplates({ task_type: 'google_sheet' })
    templates.value = Array.isArray(res) ? res : (res.data || [])
  } catch { templates.value = [] }
}

function onTemplateChange(val) {
  if (val) loadTemplate(val)
}

function onSheetChange(spreadsheetId) {
  const sheet = findSheet(spreadsheetId)
  if (sheet) {
    form.spreadsheet_title = sheet.spreadsheet_title || sheet.name || ''
    form.sheet_name = sheet.sheet_name || ''
    form.google_sheet_id = sheet.id || ''
  }
}

onMounted(() => {
  loadTemplates()
})
</script>

<style lang="scss" scoped>
.card-section-title {
  font-weight: 600;
  font-size: 15px;
  color: var(--app-text);
}

.form-hint {
  font-size: 12px;
  color: var(--app-text-muted);
  margin-top: 4px;
}

.param-card {
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  padding: 14px;
  background: var(--app-surface);

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
    font-weight: 600;
    font-size: 13px;
    color: var(--app-text);
  }

  &--primary { border-left: 3px solid var(--el-color-primary); }
  &--success { border-left: 3px solid var(--el-color-success); }
  &--info    { border-left: 3px solid var(--el-color-info); }
  &--warning { border-left: 3px solid var(--el-color-warning); }
  &--danger  { border-left: 3px solid var(--el-color-danger); }
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 0;
}
</style>
