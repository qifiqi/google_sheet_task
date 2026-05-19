<template>
  <div class="app-page task-create-page">
    <div class="page-toolbar">
      <div class="page-toolbar__meta">
        <div class="page-toolbar__eyebrow">Task Builder</div>
        <h2 class="page-title">{{ pageTitle }}</h2>
        <p class="page-description">配置 Google Sheet、Token 和参数组合，直接生成并执行批量任务。</p>
      </div>
      <div class="page-toolbar__actions">
        <el-button class="page-back-button" @click="$router.back()">返回</el-button>
      </div>
    </div>

    <el-card shadow="never" class="page-section">
      <div class="section-heading">
        <h3 class="section-title section-title--muted">任务基本信息</h3>
      </div>
      <el-row :gutter="16">
        <el-col :xs="24" :sm="8">
          <el-form-item label="选择模板">
            <el-select v-model="selectedTemplate" placeholder="不使用模板" clearable class="full-width" @change="applyTemplate">
              <el-option v-for="t in templates" :key="t.id" :value="t.id" :label="t.name" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="8">
          <el-form-item label="任务名称">
            <el-input v-model="form.name" placeholder="留空将自动生成" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="8">
          <el-form-item label="任务描述">
            <el-input v-model="form.description" type="textarea" :rows="1" placeholder="可选" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="page-section">
      <div class="section-heading">
        <h3 class="section-title section-title--muted">Google Sheet 配置</h3>
      </div>
      <el-row :gutter="16">
        <el-col :xs="24" :sm="10">
          <el-form-item label="选择 Google Sheet">
            <div class="control-row control-row--stretch">
              <el-select v-model="form.spreadsheet_id" placeholder="请选择" filterable class="full-width" @change="onSheetChange">
                <el-option v-for="s in sheets" :key="s.spreadsheet_id" :value="s.spreadsheet_id" :label="`${s.name} (${s.spreadsheet_id})`" />
              </el-select>
              <el-button :loading="sheetListLoading" @click="refreshSheets">刷新</el-button>
            </div>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="7">
          <el-form-item label="表标题">
            <el-input v-model="form.spreadsheet_title" placeholder="自动带出，可修改" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="7">
          <el-form-item label="工作表名称">
            <el-input v-model="form.sheet_name" placeholder="选择后自动带出" :readonly="worksheetLoading" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-collapse v-model="advancedOpen" class="task-create-page__collapse">
        <el-collapse-item title="更多配置" name="advanced">
          <el-row :gutter="16">
            <el-col :xs="24" :sm="6">
              <el-form-item label="认证方式">
                <el-select v-model="form.token_type" class="full-width">
                  <el-option value="file" label="Token 文件路径" />
                  <el-option value="json" label="Token JSON 字符串" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col v-if="form.token_type === 'file'" :xs="24" :sm="18">
              <el-form-item label="Token 选择">
                <el-select v-model="form.token_id" class="full-width task-create-page__field-gap" placeholder="选择 Token">
                  <el-option :value="RANDOM_TOKEN" label="随机 Token（系统自动选择未达上限的 Token）" />
                  <el-option
                    v-for="t in tokens"
                    :key="t.id"
                    :value="String(t.id)"
                    :label="`${t.name} | 占用 ${t.current_in_use_count || 0} | 累计 ${t.task_usage_count} | 上限 ${t.max_usage_count > 0 ? t.max_usage_count : '无限'}`"
                    :disabled="!t.is_available"
                  />
                </el-select>
                <div class="control-row control-row--stretch">
                  <el-input v-model="tokenImportPath" placeholder="输入 Token 文件路径后点击导入" />
                  <el-button @click="importToken">导入</el-button>
                </div>
              </el-form-item>
            </el-col>
            <el-col v-else :xs="24" :sm="18">
              <el-form-item label="Token JSON">
                <el-input v-model="form.token_json" type="textarea" :rows="3" placeholder='{"installed": {...}}' />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="代理 URL">
                <el-input v-model="form.proxy_url" placeholder="可选" />
              </el-form-item>
            </el-col>
          </el-row>
        </el-collapse-item>
      </el-collapse>
    </el-card>

    <el-card shadow="never" class="page-section">
      <div class="section-heading">
        <h3 class="section-title section-title--muted">参数配置</h3>
        <div class="section-actions">
          <el-button size="small" @click="addParam">添加参数</el-button>
          <el-button size="small" @click="clearParams">清空所有</el-button>
        </div>
      </div>
      <el-row :gutter="12">
        <el-col v-for="(p, i) in params" :key="i" :xs="24" :sm="12" :md="8" class="task-create-page__param-col">
          <el-card shadow="never" class="task-create-page__param-card" :style="{ borderColor: paramColors[i % paramColors.length] }">
            <div class="section-heading task-create-page__param-head">
              <span class="task-create-page__param-title">参数 {{ i + 1 }}</span>
              <el-button link type="danger" size="small" @click="removeParam(i)">删除</el-button>
            </div>
            <el-input v-model="params[i]" type="textarea" :rows="3" :placeholder='`["value1", "value2"]`' @input="onParamChange" />
            <div class="panel-note task-create-page__param-note">JSON 数组格式</div>
          </el-card>
        </el-col>
      </el-row>
    </el-card>

    <el-card v-if="combinationCount > 0" shadow="never" class="page-section">
      <div class="info-banner">
        <span><el-tag type="primary">{{ combinationCount }}</el-tag> 个参数组合将被执行</span>
        <el-button size="small" @click="previewVisible = true">预览组合</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <div class="action-bar">
        <el-button @click="clearSaved">清除数据</el-button>
        <el-button @click="saveTemplateVisible = true">保存为模板</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">创建任务并执行</el-button>
      </div>
    </el-card>

    <el-dialog v-model="previewVisible" title="参数组合预览" width="600px" :fullscreen="isMobile">
      <div v-for="(c, i) in previewCombinations.slice(0, 20)" :key="i" class="code-block task-create-page__preview-item">
        <strong>组合 {{ i + 1 }}:</strong> {{ c.join(', ') }}
      </div>
      <div v-if="previewCombinations.length > 20" class="panel-note panel-note--center">
        ... 还有 {{ previewCombinations.length - 20 }} 个组合
      </div>
    </el-dialog>

    <el-dialog v-model="saveTemplateVisible" title="保存为模板" width="480px" :fullscreen="isMobile">
      <el-form label-width="80px">
        <el-form-item label="模板名称"><el-input v-model="templateForm.name" /></el-form-item>
        <el-form-item label="模板描述"><el-input v-model="templateForm.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="saveTemplateVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingTemplate" @click="doSaveTemplate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getGoogleSheets, getWorksheets, getTokens, importToken as apiImportToken } from '@/api/googleSheet'
import { createTask, getTask } from '@/api/task'
import { getTemplates, getTemplate, createTemplate } from '@/api/template'
import { useResponsive } from '@/composables/useResponsive'

const route = useRoute()
const router = useRouter()
const { isMobile } = useResponsive()

const RANDOM_TOKEN = '__random__'
const LS_KEY = 'google_sheet_form_data'
const paramColors = ['#409eff', '#67c23a', '#17a2b8', '#e6a23c', '#f56c6c', '#909399']

const pageTitle = ref('创建新任务')
const sheets = ref([])
const tokens = ref([])
const templates = ref([])
const selectedTemplate = ref('')
const advancedOpen = ref([])
const worksheetLoading = ref(false)
const sheetListLoading = ref(false)
const submitting = ref(false)
const previewVisible = ref(false)
const saveTemplateVisible = ref(false)
const savingTemplate = ref(false)
const tokenImportPath = ref('')

const form = reactive({
  name: '', description: '',
  spreadsheet_id: '', spreadsheet_title: '', sheet_name: '',
  token_type: 'file', token_id: RANDOM_TOKEN, token_json: '', proxy_url: ''
})

const params = ref(['', '', '', '', '', ''])
const templateForm = reactive({ name: '', description: '' })

function parseJsonArray(str) {
  if (!str || !str.trim()) return []
  try { const v = JSON.parse(str); return Array.isArray(v) ? v : [] } catch { return null }
}

const combinationCount = computed(() => {
  const arrays = params.value.map(p => parseJsonArray(p) || []).filter(a => a.length > 0)
  if (!arrays.length) return 0
  return arrays.reduce((acc, a) => acc * a.length, 1)
})

const previewCombinations = computed(() => {
  const arrays = params.value.map(p => parseJsonArray(p) || []).filter(a => a.length > 0)
  if (!arrays.length) return []
  const result = []
  function gen(idx, cur) {
    if (idx === arrays.length) { result.push([...cur]); return }
    for (const v of arrays[idx]) { cur.push(v); gen(idx + 1, cur); cur.pop() }
  }
  gen(0, [])
  return result
})

function addParam() { params.value.push('') }
function removeParam(i) { params.value.splice(i, 1) }
function clearParams() { params.value = params.value.map(() => '') }
function onParamChange() { saveFormData() }

async function loadSheets() {
  sheetListLoading.value = true
  try {
    const res = await getGoogleSheets({ only_available: 1, table_type: 'c3' })
    sheets.value = res.items || []
  } catch {
  } finally {
    sheetListLoading.value = false
  }
}

function ensureSheetOption(spreadsheetId, title = '') {
  if (!spreadsheetId) return
  if (sheets.value.some((sheet) => sheet.spreadsheet_id === spreadsheetId)) return
  sheets.value = [
    ...sheets.value,
    {
      spreadsheet_id: spreadsheetId,
      name: title || `历史配置 ${spreadsheetId.slice(0, 8)}`
    }
  ]
}

async function refreshSheets() {
  await loadSheets()
  if (form.spreadsheet_id) ensureSheetOption(form.spreadsheet_id, form.spreadsheet_title)
  ElMessage.success('Google Sheet 列表已刷新')
}

async function loadTokens() {
  try {
    const res = await getTokens()
    tokens.value = res.tokens || []
  } catch {}
}

async function loadTemplates() {
  try {
    const res = await getTemplates()
    templates.value = res.templates || []
  } catch {}
}

async function onSheetChange() {
  if (!form.spreadsheet_id) { form.sheet_name = ''; return }
  worksheetLoading.value = true
  try {
    const res = await getWorksheets({ spreadsheet_id: form.spreadsheet_id, token_id: form.token_id, proxy_url: form.proxy_url || undefined })
    if (res.title) form.spreadsheet_title = res.title
    form.sheet_name = (res.worksheets || [])[0] || ''
    ElMessage.success('工作表已加载')
  } catch { ElMessage.error('获取工作表失败') }
  finally { worksheetLoading.value = false }
}

async function importToken() {
  if (!tokenImportPath.value.trim()) { ElMessage.warning('请输入 Token 文件路径'); return }
  try {
    const res = await apiImportToken({ token_file: tokenImportPath.value.trim() })
    ElMessage.success(res.message || 'Token 导入成功')
    tokenImportPath.value = ''
    await loadTokens()
    if (res.token?.id) form.token_id = String(res.token.id)
  } catch { ElMessage.error('导入 Token 失败') }
}

async function applyTemplate(id) {
  if (!id) return
  try {
    const tpl = await getTemplate(id)
    const config = typeof tpl.config === 'string' ? JSON.parse(tpl.config) : (tpl.config || {})
    if (tpl.name) form.name = tpl.name
    if (config.spreadsheet_id) {
      ensureSheetOption(config.spreadsheet_id, config.title || config.spreadsheet_title)
      form.spreadsheet_id = config.spreadsheet_id
      await onSheetChange()
    }
    if (config.title || config.spreadsheet_title) form.spreadsheet_title = config.title || config.spreadsheet_title
    if (config.sheet_name) form.sheet_name = config.sheet_name
    if (config.token_type) form.token_type = config.token_type
    if (config.token_id) form.token_id = String(config.token_id)
    if (config.token_json) form.token_json = config.token_json
    if (config.proxy_url) form.proxy_url = config.proxy_url
    if (Array.isArray(config.parameters)) {
      params.value = config.parameters.map(p => Array.isArray(p) ? JSON.stringify(p) : '')
    }
    ElMessage.success('已加载模板配置')
  } catch { ElMessage.error('加载模板失败') }
}

async function loadRestartTask(taskId) {
  try {
    const res = await getTask(taskId)
    const task = res.task || res
    const config = task.config || {}
    pageTitle.value = '重启任务'
    if (task.name) form.name = `${task.name} (重启)`
    if (config.spreadsheet_id) {
      ensureSheetOption(config.spreadsheet_id, config.title || config.spreadsheet_title)
      form.spreadsheet_id = config.spreadsheet_id
      await onSheetChange()
    }
    if (config.title || config.spreadsheet_title) form.spreadsheet_title = config.title || config.spreadsheet_title
    if (config.sheet_name) form.sheet_name = config.sheet_name
    if (config.token_type) form.token_type = config.token_type
    if (config.token_id) form.token_id = String(config.token_id)
    if (config.token_json) form.token_json = config.token_json
    if (config.proxy_url) form.proxy_url = config.proxy_url
    if (Array.isArray(config.parameters)) {
      params.value = config.parameters.map(p => Array.isArray(p) ? JSON.stringify(p) : '')
    }
    ElMessage.info('已加载原任务配置')
  } catch { ElMessage.error('加载原任务失败') }
}

function saveFormData() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ ...form, params: params.value }))
  } catch {}
}

function loadSavedFormData() {
  try {
    const saved = localStorage.getItem(LS_KEY)
    if (!saved) return
    const data = JSON.parse(saved)
    Object.assign(form, { name: data.name || '', description: data.description || '', spreadsheet_id: data.spreadsheet_id || '', spreadsheet_title: data.spreadsheet_title || '', sheet_name: data.sheet_name || '', token_type: data.token_type || 'file', token_id: data.token_id || RANDOM_TOKEN, token_json: data.token_json || '', proxy_url: data.proxy_url || '' })
    if (Array.isArray(data.params)) params.value = data.params
    if (form.spreadsheet_id) ensureSheetOption(form.spreadsheet_id, form.spreadsheet_title)
    ElMessage.info('表单数据已恢复')
  } catch {}
}

function clearSaved() {
  localStorage.removeItem(LS_KEY)
  Object.assign(form, { name: '', description: '', spreadsheet_id: '', spreadsheet_title: '', sheet_name: '', token_type: 'file', token_id: RANDOM_TOKEN, token_json: '', proxy_url: '' })
  params.value = ['', '', '', '', '', '']
  ElMessage.success('已清除保存的表单数据')
}

async function submit() {
  if (combinationCount.value === 0) { ElMessage.error('请至少输入一个参数'); return }
  if (!form.spreadsheet_id) { ElMessage.error('请选择 Google Sheet'); return }
  if (!form.sheet_name) { ElMessage.error('请先加载工作表名称'); return }
  if (form.token_type === 'file' && !form.token_id) { ElMessage.error('请选择 Token'); return }
  if (form.token_type === 'json' && !form.token_json) { ElMessage.error('请输入 Token JSON'); return }

  const parsedParams = params.value.map(p => parseJsonArray(p)).filter(a => a && a.length > 0)
  if (parsedParams.some(p => p === null)) { ElMessage.error('参数格式错误，请检查 JSON 格式'); return }

  submitting.value = true
  try {
    const res = await createTask({
      name: form.name || `Google Sheet 任务 - ${new Date().toLocaleString()}`,
      description: form.description || `批量执行 ${combinationCount.value} 个参数组合`,
      task_type: 'google_sheet',
      config: {
        spreadsheet_id: form.spreadsheet_id,
        title: form.spreadsheet_title || null,
        sheet_name: form.sheet_name,
        token_type: form.token_type,
        token_id: form.token_type === 'file' ? form.token_id : null,
        token_file: '',
        token_json: form.token_json,
        proxy_url: form.proxy_url || null,
        parameters: parsedParams
      }
    })
    ElMessage.success('任务创建成功，正在跳转...')
    clearSaved()
    setTimeout(() => router.push(`/task/${res.task_id}`), 800)
  } catch { ElMessage.error('创建任务失败') }
  finally { submitting.value = false }
}

async function doSaveTemplate() {
  if (!templateForm.name) { ElMessage.warning('请输入模板名称'); return }
  if (!form.spreadsheet_id) { ElMessage.error('请先选择 Google Sheet'); return }
  const parsedParams = params.value.map(p => parseJsonArray(p)).filter(a => a && a.length > 0)
  savingTemplate.value = true
  try {
    await createTemplate({
      name: templateForm.name,
      description: templateForm.description,
      config: { task_type: 'google_sheet', spreadsheet_id: form.spreadsheet_id, title: form.spreadsheet_title, sheet_name: form.sheet_name, token_type: form.token_type, token_id: form.token_id, token_json: form.token_json, proxy_url: form.proxy_url, parameters: parsedParams }
    })
    ElMessage.success('模板保存成功')
    saveTemplateVisible.value = false
    templateForm.name = ''
    templateForm.description = ''
    await loadTemplates()
  } catch { ElMessage.error('保存模板失败') }
  finally { savingTemplate.value = false }
}

watch([form, params], saveFormData, { deep: true })

onMounted(async () => {
  await Promise.all([loadSheets(), loadTokens(), loadTemplates()])
  const { template_id, restart_task_id } = route.query
  if (template_id) {
    selectedTemplate.value = template_id
    await applyTemplate(template_id)
  } else if (restart_task_id) {
    await loadRestartTask(restart_task_id)
  } else {
    loadSavedFormData()
  }
})
</script>

<style scoped>
.full-width {
  width: 100%;
}

.task-create-page__collapse {
  margin-top: 8px;
}

.task-create-page__field-gap {
  margin-bottom: 8px;
}

.task-create-page__param-col {
  margin-bottom: 12px;
}

.task-create-page__param-card {
  height: 100%;
}

.task-create-page__param-head {
  margin-bottom: 8px;
}

.task-create-page__param-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--app-text);
}

.task-create-page__param-note {
  margin-top: 4px;
}

.task-create-page__preview-item {
  margin-bottom: 8px;
}
</style>
