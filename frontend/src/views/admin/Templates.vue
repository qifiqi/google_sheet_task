<template>
  <div class="app-page templates-page">
    <PageToolbar eyebrow="管理后台" title="模板管理">
      <template #actions>
        <el-button type="primary" @click="openCreate">新建模板</el-button>
      </template>
    </PageToolbar>

    <!-- 统计卡（对齐静态版：模板总数 / C5 / C4 / 最近更新） -->
    <el-row :gutter="16" class="templates-stats">
      <el-col :xs="12" :md="6" class="templates-stats__col">
        <div class="templates-stat-card">
          <div class="templates-stat-card__label">模板总数</div>
          <div class="templates-stat-card__value">{{ templateStats.total }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :md="6" class="templates-stats__col">
        <div class="templates-stat-card">
          <div class="templates-stat-card__label">C5 模板</div>
          <div class="templates-stat-card__value templates-stat-card__value--success">{{ templateStats.c5Count }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :md="6" class="templates-stats__col">
        <div class="templates-stat-card">
          <div class="templates-stat-card__label">C4 模板</div>
          <div class="templates-stat-card__value templates-stat-card__value--info">{{ templateStats.c4Count }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :md="6" class="templates-stats__col">
        <div class="templates-stat-card">
          <div class="templates-stat-card__label">最近更新</div>
          <div class="templates-stat-card__date">{{ templateStats.latestDate }}</div>
          <div class="templates-stat-card__name">{{ templateStats.latestName }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- 搜索 + 类型筛选（对齐静态版工具条） -->
    <div class="templates-toolbar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索模板名称、工作表、描述..."
        clearable
        style="max-width: 320px"
      />
      <el-radio-group v-model="activeTypeFilter">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="c3">C3</el-radio-button>
        <el-radio-button value="c4">C4</el-radio-button>
        <el-radio-button value="c5">C5</el-radio-button>
      </el-radio-group>
    </div>

    <div v-loading="loading">
      <el-row :gutter="16">
        <el-col v-for="entry in createEntries" :key="entry.version" :xs="24" :sm="12" :md="8" class="templates-col">
          <el-card shadow="hover" class="template-entry-card" @click="$router.push(`/task/create/${entry.version}`)">
            <el-icon class="template-entry-card__icon" :color="entry.color"><Plus /></el-icon>
            <div class="template-entry-card__title">{{ entry.label }}</div>
            <div class="template-entry-card__desc">{{ entry.desc }}</div>
          </el-card>
        </el-col>

        <el-col v-for="tpl in filteredTemplates" :key="tpl.id" :xs="24" :sm="12" :md="8" class="templates-col">
          <el-card shadow="hover" class="template-card">
            <template #header>
              <div class="template-card__header">
                <span class="template-card__title">
                  {{ tpl.name }}
                  <el-tag v-if="tpl._type" :type="tpl._typeColor" size="small" class="template-card__tag">{{ tpl._type }}</el-tag>
                </span>
                <el-dropdown @command="(cmd) => handleMenuCmd(cmd, tpl)">
                  <el-icon class="template-card__menu"><MoreFilled /></el-icon>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="edit">编辑</el-dropdown-item>
                      <el-dropdown-item command="duplicate">复制</el-dropdown-item>
                      <el-dropdown-item command="delete" divided class="template-card__danger-item">删除</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
            <div class="template-card__desc">{{ tpl.description || '无描述' }}</div>
            <div class="template-card__config" v-html="tpl._configInfo"></div>
            <div class="template-card__time">创建于：{{ tpl.created_at }}</div>
            <el-button type="primary" size="small" class="full-width template-card__action" @click="useTemplate(tpl)">使用此模板</el-button>
          </el-card>
        </el-col>

        <el-col v-if="!loading && !filteredTemplates.length" :span="24">
          <el-empty :description="templates.length ? '暂无匹配模板，请调整搜索关键词或类型筛选' : '暂无模板，点击上方新建'" />
        </el-col>
      </el-row>
    </div>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑模板' : '创建模板'" width="640px" :fullscreen="isMobile">
      <el-form :model="form" label-width="80px">
        <el-form-item label="模板名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="模板描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="配置 JSON">
          <el-input v-model="form.config" type="textarea" :rows="12" spellcheck="false" placeholder="JSON 格式" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, MoreFilled } from '@element-plus/icons-vue'
import PageToolbar from '@/components/PageToolbar.vue'
import { getTemplates, createTemplate, getTemplate, updateTemplate, deleteTemplate } from '@/api/template'
import { useResponsive } from '@/composables/useResponsive'
import { usePolling } from '@/composables/usePolling'

const router = useRouter()

const { isMobile } = useResponsive()
const templates = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)
const form = reactive({ name: '', description: '', config: '' })
const searchKeyword = ref('')
const activeTypeFilter = ref('all')

const createEntries = [
  { version: 'c3', label: '新建模板', desc: '创建一个新的任务模板', color: '#409eff' },
  { version: 'c4', label: '新建 C4 模板', desc: '为 Google Sheet C4 任务创建专用模板', color: '#17a2b8' },
  { version: 'c5', label: '新建 C5 模板', desc: '为 Google Sheet C5 任务创建专用模板', color: '#67c23a' },
]

// 模板元信息解析（对齐静态版 getTemplateMeta：类型/工作表/参数规模口径一致）
function parseTemplateMeta(tpl) {
  try {
    const cfg = typeof tpl.config === 'string' ? JSON.parse(tpl.config) : (tpl.config || {})
    const isC4 = cfg.task_type === 'google_sheet_C4'
    const isC5 = cfg.task_type === 'google_sheet_C5'
    const type = isC4 ? 'c4' : (isC5 ? 'c5' : 'c3')
    const sheetName = Array.isArray(cfg.sheets) && cfg.sheets.length
      ? (cfg.sheets[0].sheet_name || '默认')
      : (cfg.sheet_name || '默认')
    let parameterValue = '0'
    if (isC4) {
      parameterValue = String(Array.isArray(cfg.parameters?.[0]) ? cfg.parameters[0].length : 0)
    } else if (isC5) {
      const p1 = Array.isArray(cfg.parameters?.[0]) ? cfg.parameters[0].length : 0
      const p2 = Array.isArray(cfg.parameters?.[1]) ? cfg.parameters[1].length : 0
      const p3 = Array.isArray(cfg.parameters?.[2]) ? cfg.parameters[2].length : 0
      parameterValue = `${p1}/${p2}/${p3}`
    } else {
      parameterValue = String(Array.isArray(cfg.parameters) ? cfg.parameters.filter(p => Array.isArray(p) && p.length).length : 0)
    }
    return { type, typeLabel: type.toUpperCase(), sheetName, parameterValue }
  } catch {
    return { type: 'c3', typeLabel: 'C3', sheetName: '', parameterValue: '0' }
  }
}

const templateStats = computed(() => {
  const metas = templates.value.map((t) => t._meta)
  const latest = [...templates.value].sort(
    (a, b) => new Date(b.updated_at || b.created_at || 0) - new Date(a.updated_at || a.created_at || 0)
  )[0]
  return {
    total: templates.value.length,
    c4Count: metas.filter((meta) => meta.type === 'c4').length,
    c5Count: metas.filter((meta) => meta.type === 'c5').length,
    latestDate: latest ? new Date(latest.updated_at || latest.created_at).toLocaleDateString() : '-',
    latestName: latest ? latest.name : '暂无模板',
  }
})

const filteredTemplates = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  return templates.value.filter((tpl) => {
    const meta = tpl._meta
    if (activeTypeFilter.value !== 'all' && meta.type !== activeTypeFilter.value) return false
    if (!keyword) return true
    const haystack = [tpl.name, tpl.description, meta.sheetName, meta.parameterValue, meta.typeLabel]
      .join(' ')
      .toLowerCase()
    return haystack.includes(keyword)
  })
})

function buildConfigInfo(meta) {
  const sheetLine = `工作表: ${meta.sheetName || '默认'}`
  if (meta.type === 'c4') return `${sheetLine}<br>产品代码数: ${meta.parameterValue}`
  if (meta.type === 'c5') return `${sheetLine}<br>参数1/2/3: ${meta.parameterValue}`
  return `${sheetLine}<br>参数组数: ${meta.parameterValue}`
}

async function loadTemplates() {
  loading.value = true
  try {
    const res = await getTemplates()
    templates.value = (res.templates || []).map((t) => {
      const meta = parseTemplateMeta(t)
      return {
        ...t,
        _meta: meta,
        _type: meta.typeLabel,
        _typeColor: meta.type === 'c5' ? 'success' : '',
        _configInfo: buildConfigInfo(meta),
      }
    })
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.description = ''
  form.config = ''
  dialogVisible.value = true
}

async function handleMenuCmd(cmd, tpl) {
  if (cmd === 'edit') {
    const res = await getTemplate(tpl.id)
    editingId.value = res.id
    form.name = res.name
    form.description = res.description || ''
    form.config = JSON.stringify(res.config, null, 2)
    dialogVisible.value = true
  } else if (cmd === 'duplicate') {
    const res = await getTemplate(tpl.id)
    saving.value = true
    try {
      await createTemplate({ name: `${res.name} (副本)`, description: res.description, config: res.config })
      ElMessage.success('模板复制成功')
      loadTemplates()
    } finally {
      saving.value = false
    }
  } else if (cmd === 'delete') {
    await ElMessageBox.confirm('确定要删除这个模板吗？', '确认删除', { type: 'warning' })
    await deleteTemplate(tpl.id)
    ElMessage.success('模板已删除')
    loadTemplates()
  }
}

async function handleSave() {
  if (!form.name) {
    ElMessage.warning('请输入模板名称')
    return
  }
  if (!form.config) {
    ElMessage.warning('请输入配置信息')
    return
  }
  try {
    JSON.parse(form.config)
  } catch {
    ElMessage.error('配置信息不是有效的 JSON 格式')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await updateTemplate(editingId.value, { name: form.name, description: form.description, config: form.config })
    } else {
      await createTemplate({ name: form.name, description: form.description, config: form.config })
    }
    ElMessage.success(editingId.value ? '模板更新成功' : '模板创建成功')
    dialogVisible.value = false
    loadTemplates()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

function useTemplate(tpl) {
  const cfg = typeof tpl.config === 'string' ? JSON.parse(tpl.config) : tpl.config
  const versionMap = {
    google_sheet: 'c3',
    google_sheet_C4: 'c4',
    google_sheet_C5: 'c5',
    google_sheet_C31: 'c31',
  }
  const version = versionMap[cfg?.task_type] || 'c3'
  // SPA 路由到版本化创建页；各创建页 onMounted 读取 template_id 自动回填
  router.push({ path: `/task/create/${version}`, query: { template_id: String(tpl.id) } })
}

usePolling(loadTemplates, { interval: 60000 })
</script>

<style scoped>
.templates-stats {
  margin-bottom: 16px;
}

.templates-stats__col {
  margin-bottom: 8px;
}

.templates-stat-card {
  border: 1px solid var(--app-border);
  border-radius: 12px;
  padding: 14px 16px;
  background: var(--app-surface);
  height: 100%;
}

.templates-stat-card__label {
  font-size: var(--app-font-xs);
  color: var(--app-text-muted);
}

.templates-stat-card__value {
  margin-top: 6px;
  font-size: 28px;
  font-weight: 700;
}

.templates-stat-card__value--success {
  color: #16a34a;
}

.templates-stat-card__value--info {
  color: #0284c7;
}

.templates-stat-card__date {
  margin-top: 6px;
  font-size: var(--app-font-md, 16px);
  font-weight: 700;
}

.templates-stat-card__name {
  margin-top: 2px;
  font-size: var(--app-font-xs);
  color: var(--app-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.templates-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.templates-col {
  margin-bottom: 16px;
}

.template-entry-card {
  min-height: 160px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.template-entry-card__icon {
  font-size: 36px;
  margin-bottom: 8px;
}

.template-entry-card__title,
.template-card__title {
  font-weight: 700;
}

.template-entry-card__desc,
.template-card__desc,
.template-card__config,
.template-card__time {
  font-size: var(--app-font-xs);
}

.template-entry-card__desc,
.template-card__desc,
.template-card__config {
  color: var(--app-text-muted);
}

.template-card__time {
  color: #9aa8bb;
}

.template-card__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.template-card__tag {
  margin-left: 6px;
}

.template-card__menu {
  cursor: pointer;
}

.template-card__danger-item {
  color: #f56c6c;
}

.template-card__desc {
  margin-bottom: 8px;
}

.template-card__config {
  margin-bottom: 12px;
}

.template-card__action {
  margin-top: 12px;
}
</style>
